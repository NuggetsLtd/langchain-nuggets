"""Lightweight local authority server for demo purposes.

Implements two endpoints with in-memory state:

- `POST /api/authority/evaluate` — runs the same constraint-evaluation
  flow as the partner repo's Next.js route (delegation lookup, scope
  / cap / expiry / revocation checks, ALLOW/DENY decision + proof).
- `POST /token` — minimal OIDC `client_credentials` token endpoint.
  Accepts the SDK's `private_key_jwt` assertion **without verifying
  the signature** and returns an opaque access token. Just enough to
  satisfy the middleware's bearer-fetch path so the demo can run the
  real auth flow offline.

**Still not a substitute for testing against the deployed backend.**
This mock does not verify `agent_proof` JWS, does not verify the OIDC
client_assertion, and does not enforce client_id ↔ DID mapping. Use it
for SDK-shape + scenario exploration only.

For real end-to-end verification against a deployed environment, see
`scripts/smoke_test_authority.py` (CLI) or
`test_authority_integration.py` (pytest, skips when env unset).
"""
import hashlib
import json
import time
from datetime import datetime, timezone
from threading import Thread
from typing import Any, Dict, List, Optional

from demo_config import (
    AGENT_A,
    AGENT_B,
    ORG_A,
    generate_proof_id,
    sign_proof,
)

try:
    # `Form(...)` requires python-multipart; FastAPI doesn't pull it in by default.
    from fastapi import FastAPI, Form
    from fastapi.responses import JSONResponse
    import uvicorn
except ImportError:
    raise ImportError("pip install fastapi uvicorn  # required for the demo server")

app = FastAPI(title="Nuggets Authority Demo Server")

# ---------- In-memory delegation store ----------

_delegations: Dict[str, dict] = {}
_caps: Dict[str, Dict[str, dict]] = {}  # delegation_id -> { cap_type -> cap }
_audit_log: List[dict] = []


def issue_delegation(
    delegation_id: str,
    agent_did: str,
    allowed_capabilities: List[str],
    allowed_targets: Optional[List[str]] = None,
    constraints: Optional[dict] = None,
    caps: Optional[List[dict]] = None,
    expires_at: Optional[str] = None,
) -> dict:
    """Issue a delegation (in-memory)."""
    delegation = {
        "id": delegation_id,
        "organisation_id": ORG_A["id"],
        "agent_did": agent_did,
        "local_agent_id": AGENT_A["did"],
        "allowed_capabilities": allowed_capabilities,
        "allowed_targets": allowed_targets or [],
        "constraints": constraints or {},
        "expires_at": expires_at,
        "revoked_at": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _delegations[delegation_id] = delegation

    if caps:
        _caps[delegation_id] = {}
        for cap in caps:
            _caps[delegation_id][cap["cap_type"]] = {
                "cap_type": cap["cap_type"],
                "cap_limit": cap["cap_limit"],
                "cap_used": 0,
            }

    return delegation


def revoke_delegation(delegation_id: str) -> None:
    """Revoke a delegation."""
    if delegation_id in _delegations:
        _delegations[delegation_id]["revoked_at"] = datetime.now(timezone.utc).isoformat()


def get_audit_log() -> List[dict]:
    return list(_audit_log)


# ---------- Authority evaluation endpoint ----------


@app.post("/token")
async def token(
    grant_type: str = Form(...),
    client_assertion_type: str = Form(...),
    client_assertion: str = Form(...),
    scope: str = Form(""),
) -> JSONResponse:
    """Minimal OIDC `client_credentials` token endpoint.

    Accepts the SDK's `private_key_jwt` assertion without verifying the
    signature. Returns a stub access token so the middleware's bearer
    fetch can succeed and the demo can run the real auth flow offline.
    """
    if grant_type != "client_credentials":
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)
    if client_assertion_type != "urn:ietf:params:oauth:client-assertion-type:jwt-bearer":
        return JSONResponse({"error": "invalid_client"}, status_code=400)
    if not client_assertion:
        return JSONResponse({"error": "invalid_client"}, status_code=400)

    return JSONResponse(
        {
            "access_token": "demo-access-token",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": scope or "authority.evaluate",
        }
    )


@app.post("/api/authority/evaluate")
async def evaluate(request_body: dict) -> JSONResponse:
    start = time.monotonic()

    agent_id = request_body.get("agent_id", "")
    controller_id = request_body.get("controller_id", "")
    delegation_id = request_body.get("delegation_id", "")
    action = request_body.get("action", {})

    delegation = _delegations.get(delegation_id)
    caps = _caps.get(delegation_id, {})

    constraints_evaluated: List[str] = []
    reason_code: Optional[str] = None

    # --- Evaluate constraints ---

    # 1. Delegation exists
    if not delegation:
        return _deny("DELEGATION_NOT_FOUND", ["delegation_exists"], delegation_id, agent_id, action, start)

    # 2. Not revoked
    constraints_evaluated.append("not_revoked")
    if delegation["revoked_at"]:
        return _deny("DELEGATION_REVOKED", constraints_evaluated, delegation_id, agent_id, action, start)

    # 3. Not expired
    constraints_evaluated.append("expiry_valid")
    if delegation["expires_at"]:
        expires = datetime.fromisoformat(delegation["expires_at"])
        if expires < datetime.now(timezone.utc):
            return _deny("DELEGATION_EXPIRED", constraints_evaluated, delegation_id, agent_id, action, start)

    # 4. Tool allowed
    constraints_evaluated.append("tool_allowed")
    allowed = delegation["allowed_capabilities"]
    if allowed and action.get("tool") not in allowed:
        return _deny("TOOL_NOT_IN_SCOPE", constraints_evaluated, delegation_id, agent_id, action, start)

    # 5. Target allowed
    constraints_evaluated.append("target_allowed")
    targets = delegation["allowed_targets"]
    if targets and action.get("target") and action["target"] not in targets:
        return _deny("TARGET_NOT_IN_SCOPE", constraints_evaluated, delegation_id, agent_id, action, start)

    # 6. Caps
    for cap_type, cap in caps.items():
        constraints_evaluated.append(f"cap_{cap_type}")
        if cap["cap_used"] >= cap["cap_limit"]:
            return _deny(f"CAP_EXCEEDED_{cap_type.upper()}", constraints_evaluated, delegation_id, agent_id, action, start)

    # --- ALLOW ---
    # Increment caps
    for cap in caps.values():
        cap["cap_used"] += 1

    proof_id = generate_proof_id()

    proof_data = {
        "proof_id": proof_id,
        "agent_id": agent_id,
        "controller_id": controller_id,
        "delegation_id": delegation_id,
        "tool": action.get("tool"),
        "parameters_hash": action.get("parameters_hash"),
        "intent_hash": action.get("intent_hash"),
        "constraints_evaluated": constraints_evaluated,
        "decision": "ALLOW",
    }

    signature = sign_proof(proof_data)
    latency_ms = (time.monotonic() - start) * 1000

    _audit_log.append({
        "delegation_id": delegation_id,
        "agent_did": agent_id,
        "decision": "ALLOW",
        "constraints_evaluated": constraints_evaluated,
        "latency_ms": latency_ms,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return JSONResponse({
        "decision": "ALLOW",
        "proof_id": proof_id,
        "signature": signature,
        "reason_code": None,
        "constraints_evaluated": constraints_evaluated,
    })


def _deny(
    reason: str,
    constraints: List[str],
    delegation_id: str,
    agent_id: str,
    action: dict,
    start: float,
) -> JSONResponse:
    latency_ms = (time.monotonic() - start) * 1000

    _audit_log.append({
        "delegation_id": delegation_id,
        "agent_did": agent_id,
        "decision": "DENY",
        "reason_code": reason,
        "constraints_evaluated": constraints,
        "latency_ms": latency_ms,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    return JSONResponse({
        "decision": "DENY",
        "proof_id": generate_proof_id(),
        "signature": "",
        "reason_code": reason,
        "constraints_evaluated": constraints,
    })


def start_server(port: int = 9999) -> Thread:
    """Start the authority server in a background thread."""
    thread = Thread(
        target=uvicorn.run,
        args=(app,),
        kwargs={"host": "127.0.0.1", "port": port, "log_level": "warning"},
        daemon=True,
    )
    thread.start()
    time.sleep(0.5)  # Wait for server to start
    return thread
