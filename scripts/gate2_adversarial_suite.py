#!/usr/bin/env python3
"""Gate-2 adversarial/regression suite for the Nuggets authority endpoint.

Companion to scripts/smoke_test_authority.py. Where the smoke test proves the
happy path (ALLOW + proof), this proves the GUARANTEES hold by proving the
attacks FAIL — against the *deployed* endpoint, per the confidence principle
(partner #118).

Run in the langchain-nuggets workspace (needs the SDK 0.4.1 env + the agent's
downloaded private key). Drop into scripts/ and run after the smoke test passes.

Same env vars as the smoke test, plus optional fixtures:
    NUGGETS_AUTHORITY_URL, NUGGETS_OIDC_ISSUER_URL, NUGGETS_AGENT_ID,
    NUGGETS_CONTROLLER_ID, NUGGETS_DELEGATION_ID, NUGGETS_AGENT_PRIVATE_KEY,
    NUGGETS_TOOL (an in-scope capability), NUGGETS_TARGET (optional, in-scope)
  Fixtures (skip the scenario if unset):
    NUGGETS_OUT_OF_SCOPE_TOOL, NUGGETS_OUT_OF_SCOPE_TARGET,
    NUGGETS_EXPIRED_DELEGATION_ID, NUGGETS_REVOKED_DELEGATION_ID,
    NUGGETS_CAPPED_DELEGATION_ID, NUGGETS_OTHER_AGENT_DELEGATION_ID

Exit 0 only if every active scenario produced its expected outcome.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, Optional

import httpx
from cryptography.hazmat.primitives.asymmetric import rsa
from langchain_core.messages import ToolMessage

from langchain_nuggets.middleware import MiddlewareConfig, NuggetsAuthorityMiddleware
from langchain_nuggets.middleware.agent_proof import load_private_key, sign_agent_proof
from langchain_nuggets.middleware.authority_middleware import _extract_oidc_client_id
from langchain_nuggets.middleware.oidc_client import OidcClientCredentialsClient

results: list[tuple[str, bool, str]] = []


def record(name: str, passed: bool, detail: str = "") -> None:
    results.append((name, passed, detail))
    print(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        print(f"FATAL: required env {name} not set", file=sys.stderr)
        sys.exit(2)
    return v


def base_config(**overrides: Any) -> MiddlewareConfig:
    cfg = dict(
        api_url=env("NUGGETS_AUTHORITY_URL"),
        oidc_issuer_url=env("NUGGETS_OIDC_ISSUER_URL"),
        agent_id=env("NUGGETS_AGENT_ID"),
        controller_id=env("NUGGETS_CONTROLLER_ID"),
        delegation_id=env("NUGGETS_DELEGATION_ID"),
        agent_private_key=_load_key(),
    )
    cfg.update(overrides)
    return MiddlewareConfig(**cfg)


def _load_key() -> Any:
    raw = env("NUGGETS_AGENT_PRIVATE_KEY")
    if raw.lstrip().startswith("{"):
        return json.loads(raw)
    return raw


def _now_iso() -> str:
    """Fresh RFC3339 timestamp so the request passes the staleness window
    and reaches the gate under test rather than tripping STALE_TIMESTAMP."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _wrong_key_jwk() -> Dict[str, Any]:
    """A valid-format RSA private JWK NOT registered for the agent.

    Drives AGENT_PROOF_INVALID: the proof signs cleanly but the backend
    verifies it against the agent's registered public key and rejects it.
    """
    from jwt.algorithms import RSAAlgorithm  # PyJWT[crypto], an SDK dep

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(key))
    jwk["alg"] = "RS256"
    jwk["kid"] = "key-1"  # match the registered kid so resolution is attempted
    return {"keys": [jwk]}


def run_tool_call(cfg: MiddlewareConfig, tool: str, target: Optional[str] = None) -> Dict[str, Any]:
    mw = NuggetsAuthorityMiddleware(cfg)
    args: Dict[str, Any] = {"userId": "gate2-user"}
    if target:
        args["target"] = target
    request = SimpleNamespace(tool_call={"name": tool, "args": args, "id": "gate2-call"})

    def handler(_: object) -> ToolMessage:
        return ToolMessage(content=json.dumps({"status": "ok"}), tool_call_id="gate2-call")

    result = mw.wrap_tool_call(request, handler)
    return json.loads(result.content)


def expect_deny(name: str, payload: Dict[str, Any], expected_reason: str) -> None:
    status = payload.get("status")
    reason = (payload.get("reason_code") or payload.get("message") or "").upper()
    if status in {"DENIED", "ERROR"} and expected_reason.upper() in reason:
        record(name, True, f"{status} / {reason}")
    else:
        record(name, False, f"got status={status} reason={reason!r}, wanted {expected_reason}")


# ---------------------------------------------------------------------------
# Category A — drivable through the public SDK middleware (config/input)
# ---------------------------------------------------------------------------

def scenario_baseline_allow() -> None:
    p = run_tool_call(base_config(), env("NUGGETS_TOOL"), os.environ.get("NUGGETS_TARGET"))
    record("A0 baseline ALLOW", p.get("status") not in {"DENIED", "ERROR"}, str(p.get("status")))


def scenario_forged_proof_wrong_key() -> None:
    """Forge ONLY the agent_proof, with a valid bearer.

    The SDK uses one key for both the OIDC client-assertion and the
    agent_proof, so swapping the whole key via MiddlewareConfig would fail
    at the token exchange (invalid_client) and never reach the backend's
    proof check. To isolate AGENT_PROOF_INVALID we mint a real bearer with
    the registered key, then raw-POST a body whose agent_proof is signed by
    an unregistered key (nonce-bound, so it survives nonce checks and gets
    to signature verification).
    """
    cfg = base_config()
    real_pem = load_private_key(_load_key())
    wrong_pem = load_private_key(_wrong_key_jwk())

    token = OidcClientCredentialsClient(
        issuer_url=cfg.oidc_issuer_url,
        client_id=_extract_oidc_client_id(cfg.agent_id),
        private_key_pem=real_pem,
        scope=cfg.authority_scope,
        resource=cfg.resolved_authority_audience(),
    ).get_access_token()

    nonce = "gate2-forged-proof"
    forged_proof = sign_agent_proof(wrong_pem, cfg.agent_id, nonce)
    body = {
        "agent_id": cfg.agent_id,
        "controller_id": cfg.controller_id,
        "delegation_id": cfg.delegation_id,
        "agent_proof": forged_proof,
        "action": {
            "tool": env("NUGGETS_TOOL"),
            "nonce": nonce,
            "timestamp": _now_iso(),
            "parameters_hash": "gate2",
            "intent_hash": "gate2",
        },
    }
    url = cfg.api_url.rstrip("/") + "/api/authority/evaluate"
    r = httpx.post(
        url,
        json=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        timeout=15,
    )
    # The proof-verification failure path returns 401 with an
    # {"error": "Agent DID ownership verification failed"} body (the
    # reason_code lands in the audit row, not the HTTP body — only the
    # bearer-enforcement path echoes reason_code). Assert against that
    # contract: a 401 whose error names DID-ownership / proof failure.
    name = "A1 forged agent_proof (valid bearer, unregistered proof key)"
    err = ""
    try:
        err = (r.json().get("error") or "").lower()
    except Exception:
        err = r.text[:120]
    ok = r.status_code == 401 and ("ownership" in err or "proof" in err)
    record(name, ok, f"{r.status_code} {err!r}")


def scenario_tool_out_of_scope() -> None:
    tool = os.environ.get("NUGGETS_OUT_OF_SCOPE_TOOL")
    if not tool:
        record("A2 tool out of scope", True, "SKIPPED (set NUGGETS_OUT_OF_SCOPE_TOOL)")
        return
    expect_deny("A2 tool out of scope", run_tool_call(base_config(), tool), "TOOL_NOT_IN_SCOPE")


def scenario_target_out_of_scope() -> None:
    target = os.environ.get("NUGGETS_OUT_OF_SCOPE_TARGET")
    if not target:
        record("A3 target out of scope", True, "SKIPPED (set NUGGETS_OUT_OF_SCOPE_TARGET)")
        return
    p = run_tool_call(base_config(), env("NUGGETS_TOOL"), target)
    expect_deny("A3 target out of scope", p, "TARGET_NOT_IN_SCOPE")


def scenario_expired_delegation() -> None:
    d = os.environ.get("NUGGETS_EXPIRED_DELEGATION_ID")
    if not d:
        record("A4 expired delegation", True, "SKIPPED (set NUGGETS_EXPIRED_DELEGATION_ID)")
        return
    expect_deny("A4 expired delegation", run_tool_call(base_config(delegation_id=d), env("NUGGETS_TOOL")), "DELEGATION_EXPIRED")


def scenario_revoked_delegation() -> None:
    d = os.environ.get("NUGGETS_REVOKED_DELEGATION_ID")
    if not d:
        record("A5 revoked delegation", True, "SKIPPED (set NUGGETS_REVOKED_DELEGATION_ID)")
        return
    expect_deny("A5 revoked delegation", run_tool_call(base_config(delegation_id=d), env("NUGGETS_TOOL")), "DELEGATION_REVOKED")


def scenario_foreign_delegation() -> None:
    d = os.environ.get("NUGGETS_OTHER_AGENT_DELEGATION_ID")
    if not d:
        record("A6 delegation belongs to another agent", True, "SKIPPED (set NUGGETS_OTHER_AGENT_DELEGATION_ID)")
        return
    expect_deny("A6 foreign delegation", run_tool_call(base_config(delegation_id=d), env("NUGGETS_TOOL")), "DELEGATION_AGENT_MISMATCH")


def scenario_cap_exceeded() -> None:
    d = os.environ.get("NUGGETS_CAPPED_DELEGATION_ID")
    if not d:
        record("A7 cap exceeded", True, "SKIPPED (set NUGGETS_CAPPED_DELEGATION_ID to a delegation whose cap is exhausted)")
        return
    expect_deny("A7 cap exceeded", run_tool_call(base_config(delegation_id=d), env("NUGGETS_TOOL")), "CAP_EXCEEDED")


# ---------------------------------------------------------------------------
# Category B — raw HTTP bearer negatives (no SDK token needed)
# ---------------------------------------------------------------------------

def _raw_post(headers: Dict[str, str]) -> httpx.Response:
    body = {
        "agent_id": env("NUGGETS_AGENT_ID"),
        "controller_id": env("NUGGETS_CONTROLLER_ID"),
        "delegation_id": env("NUGGETS_DELEGATION_ID"),
        "agent_proof": "x",
        "action": {
            "tool": env("NUGGETS_TOOL"),
            "nonce": "gate2-raw",
            "timestamp": "2026-01-01T00:00:00Z",
            "parameters_hash": "x",
            "intent_hash": "x",
        },
    }
    url = env("NUGGETS_AUTHORITY_URL").rstrip("/") + "/api/authority/evaluate"
    return httpx.post(url, json=body, headers={"Content-Type": "application/json", **headers}, timeout=15)


def scenario_bearer_missing() -> None:
    r = _raw_post({})
    ok = r.status_code == 401 and r.json().get("reason_code") == "BEARER_MISSING"
    record("B1 no bearer -> 401 BEARER_MISSING", ok, f"{r.status_code} {r.text[:80]}")


def scenario_bearer_junk() -> None:
    r = _raw_post({"Authorization": "Bearer not-a-jwt"})
    ok = r.status_code == 401 and r.json().get("reason_code") == "BEARER_INVALID"
    record("B2 junk bearer -> 401 BEARER_INVALID", ok, f"{r.status_code} {r.text[:80]}")


# ---------------------------------------------------------------------------
# TODO (need SDK token internals or fixtures the high-level API can't reach):
#   B3 valid token + replayed action.nonce  -> NONCE_REPLAY
#   B4 valid token + stale action.timestamp -> STALE_TIMESTAMP
#   B5 valid token, wrong audience/scope    -> BEARER_INVALID / scope reject
#       (mint via the SDK's OidcClientCredentialsClient with a bad resource/scope)
#   C  consumer-side proof verification (tampered action hash, wrong-key proof
#      signature) -> belongs with #161 once the SDK verifies proofs by default
# ---------------------------------------------------------------------------

SCENARIOS = [
    scenario_baseline_allow,
    scenario_forged_proof_wrong_key,
    scenario_tool_out_of_scope,
    scenario_target_out_of_scope,
    scenario_expired_delegation,
    scenario_revoked_delegation,
    scenario_foreign_delegation,
    scenario_cap_exceeded,
    scenario_bearer_missing,
    scenario_bearer_junk,
]


def main() -> None:
    for s in SCENARIOS:
        try:
            s()
        except Exception as exc:  # a scenario crashing is a failure, not an abort
            record(s.__name__, False, f"raised {type(exc).__name__}: {exc}")
    failed = [n for n, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
