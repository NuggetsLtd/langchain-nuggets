#!/usr/bin/env python3
"""Cross-Org Authority Demo — Nuggets Execution-Layer MVP

Runs end-to-end against the local FastAPI mock in `local_authority.py`,
which provides both the `/api/authority/evaluate` route and a stub
OIDC `/token` endpoint. The mock does not verify `agent_proof` or the
OIDC `client_assertion`, but the SDK does sign + send both — so the
demo exercises the real auth path, just with relaxed server-side
verification.

For verification against a deployed backend (real signature checks,
real OIDC), use `scripts/smoke_test_authority.py` — see
`docs/agent-provisioning.md`.

Demonstrates all six trust primitives:
  1. Actor Identity       — agent DID verification
  2. Delegated Authority  — scoped delegation from Org A to Org B's agent
  3. Policy / Constraints — tool_allowed, target_allowed, caps, expiry
  4. Intent Binding       — same tool + different intent = different proof
  5. Consent              — revocation immediately blocks execution
  6. Accountability       — portable, independently verifiable proof

Scenarios:
  1. ALLOW      — in-scope tool call
  2. DENY       — out-of-scope tool
  3. DENY       — cap exceeded
  4. DENY       — expired delegation
  5. DENY       — revoked delegation
  6. INTENT     — different intent = different proof hash
  7. VERIFY     — independent proof verification
"""
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock

# Add parent packages to path for local development
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "packages" / "python"))

from langchain_core.messages import ToolMessage

from langchain_nuggets.middleware.authority_middleware import NuggetsAuthorityMiddleware
from langchain_nuggets.middleware.types import MiddlewareConfig

from demo_config import AGENT_A, AGENT_B, ORG_A, ORG_B
from local_authority import (
    app,
    issue_delegation,
    revoke_delegation,
    start_server,
    get_audit_log,
)
from verify_proof import verify_proof


AUTHORITY_PORT = 9999
AUTHORITY_URL = f"http://127.0.0.1:{AUTHORITY_PORT}"


def make_tool_request(tool_name: str, args: dict, call_id: str = "call-1"):
    """Create a mock ToolNode request."""
    request = MagicMock()
    request.tool_call = {"name": tool_name, "args": args, "id": call_id}
    return request


def make_handler(result: str = '{"status": "success"}', call_id: str = "call-1"):
    """Create a mock tool handler that returns a ToolMessage."""
    handler = MagicMock()
    handler.return_value = ToolMessage(content=result, tool_call_id=call_id)
    return handler


def banner(text: str):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")


def print_result(result, middleware):
    content = result.content if isinstance(result.content, str) else str(result.content)
    try:
        data = json.loads(content)
        status = data.get("status", "success")
    except (json.JSONDecodeError, TypeError):
        status = "success"
        data = {"content": content}

    if status == "DENIED":
        print(f"  Decision:  DENY")
        print(f"  Reason:    {data.get('reason_code', 'unknown')}")
        print(f"  Tool:      {data.get('tool', 'unknown')} — BLOCKED (never executed)")
    elif status == "ERROR":
        print(f"  Status:    ERROR")
        print(f"  Message:   {data.get('message', 'unknown')}")
    else:
        print(f"  Decision:  ALLOW")
        print(f"  Result:    {content[:80]}")
        if middleware.proofs:
            proof = middleware.proofs[-1]
            print(f"  Proof ID:  {proof.proof_id}")
            print(f"  Latency:   {proof.latency_ms:.1f}ms")
            if proof.intent_hash:
                print(f"  Intent:    {proof.intent_hash[:16]}...")
            if proof.constraints_evaluated:
                print(f"  Checked:   {proof.constraints_evaluated}")


def run():
    banner("Starting Nuggets Authority Demo Server")
    start_server(AUTHORITY_PORT)
    print(f"  Authority server running at {AUTHORITY_URL}")

    # --- Setup: Issue delegation from Org A to Agent B ---
    banner("Setup: Org A delegates to Org B's Agent")
    delegation = issue_delegation(
        delegation_id="del-001",
        agent_did=AGENT_B["did"],
        allowed_capabilities=["check_kyc_status", "verify_credential"],
        allowed_targets=["kyc_service"],
        caps=[{"cap_type": "invocations", "cap_limit": 3}],
        expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
    )
    print(f"  Org:          {ORG_A['name']} ({ORG_A['id']})")
    print(f"  Agent:        {AGENT_B['name']} ({AGENT_B['did']})")
    print(f"  Capabilities: {delegation['allowed_capabilities']}")
    print(f"  Cap:          3 invocations")
    print(f"  Expires:      {delegation['expires_at']}")

    # Run the real OIDC + JWS path against the local mock (mock's /token
    # endpoint accepts any well-formed client_assertion and returns a stub
    # access token; /api/authority/evaluate ignores the bearer + agent_proof
    # for verification but accepts them in the request shape). Ephemeral
    # RSA key is generated per-run.
    from cryptography.hazmat.primitives import serialization as _ser
    from cryptography.hazmat.primitives.asymmetric import rsa as _rsa

    _demo_key_pem = (
        _rsa.generate_private_key(public_exponent=65537, key_size=2048)
        .private_bytes(
            encoding=_ser.Encoding.PEM,
            format=_ser.PrivateFormat.PKCS8,
            encryption_algorithm=_ser.NoEncryption(),
        )
        .decode("utf-8")
    )

    config = MiddlewareConfig(
        api_url=AUTHORITY_URL,
        oidc_issuer_url=AUTHORITY_URL,  # mock serves /token on the same port
        agent_id=AGENT_B["did"],
        controller_id=ORG_B["id"],
        delegation_id="del-001",
        agent_private_key=_demo_key_pem,
    )
    middleware = NuggetsAuthorityMiddleware(config)

    # --- Scenario 1: ALLOW ---
    banner("Scenario 1: ALLOW — in-scope tool call")
    request = make_tool_request("check_kyc_status", {"target": "kyc_service", "user_id": "u-123"})
    handler = make_handler('{"verified": true, "level": "enhanced"}')
    result = middleware.wrap_tool_call(request, handler)
    print_result(result, middleware)

    # --- Scenario 2: DENY — out of scope ---
    banner("Scenario 2: DENY — out-of-scope tool")
    request = make_tool_request("initiate_kyc", {"target": "kyc_service", "user_id": "u-456"})
    handler = make_handler()
    result = middleware.wrap_tool_call(request, handler)
    print_result(result, middleware)

    # --- Scenario 3: DENY — cap exceeded ---
    banner("Scenario 3: DENY — cap exceeded")
    # Use remaining 2 invocations
    for i in range(2):
        req = make_tool_request("check_kyc_status", {"target": "kyc_service", "user_id": f"u-{i}"})
        h = make_handler('{"verified": true}')
        middleware.wrap_tool_call(req, h)
    print("  Used 2 more invocations (3/3 total)")

    # This one should be denied
    request = make_tool_request("check_kyc_status", {"target": "kyc_service", "user_id": "u-999"})
    handler = make_handler()
    result = middleware.wrap_tool_call(request, handler)
    print_result(result, middleware)

    # --- Scenario 4: DENY — expired ---
    banner("Scenario 4: DENY — expired delegation")
    expired_delegation = issue_delegation(
        delegation_id="del-expired",
        agent_did=AGENT_B["did"],
        allowed_capabilities=["check_kyc_status"],
        expires_at=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
    )
    expired_config = config.model_copy(update={"delegation_id": "del-expired"})
    expired_mw = NuggetsAuthorityMiddleware(expired_config)

    request = make_tool_request("check_kyc_status", {"target": "kyc_service"})
    handler = make_handler()
    result = expired_mw.wrap_tool_call(request, handler)
    print_result(result, expired_mw)

    # --- Scenario 5: DENY — revoked ---
    banner("Scenario 5: DENY — revoked delegation")
    revokable = issue_delegation(
        delegation_id="del-revoke",
        agent_did=AGENT_B["did"],
        allowed_capabilities=["check_kyc_status"],
        caps=[{"cap_type": "invocations", "cap_limit": 10}],
    )
    revoke_config = config.model_copy(update={"delegation_id": "del-revoke"})
    revoke_mw = NuggetsAuthorityMiddleware(revoke_config)

    # First call succeeds
    request = make_tool_request("check_kyc_status", {"target": "kyc_service"})
    handler = make_handler('{"verified": true}')
    result = revoke_mw.wrap_tool_call(request, handler)
    print(f"  Before revocation: ALLOW (proof_id={revoke_mw.proofs[-1].proof_id})")

    # Revoke
    revoke_delegation("del-revoke")
    print("  >>> Delegation revoked <<<")

    # Next call should be denied
    request = make_tool_request("check_kyc_status", {"target": "kyc_service"})
    handler = make_handler()
    result = revoke_mw.wrap_tool_call(request, handler)
    print_result(result, revoke_mw)

    # --- Scenario 6: Intent binding ---
    banner("Scenario 6: Intent binding — same tool, different intent")
    intent_delegation = issue_delegation(
        delegation_id="del-intent",
        agent_did=AGENT_B["did"],
        allowed_capabilities=["check_kyc_status"],
        caps=[{"cap_type": "invocations", "cap_limit": 10}],
    )
    intent_config = config.model_copy(update={
        "delegation_id": "del-intent",
        "intent_resolver": lambda tool, args: f"Check KYC for compliance review",
    })
    intent_mw = NuggetsAuthorityMiddleware(intent_config)

    request = make_tool_request("check_kyc_status", {"target": "kyc_service", "user_id": "u-123"})
    handler = make_handler('{"verified": true}')
    intent_mw.wrap_tool_call(request, handler)
    proof1 = intent_mw.proofs[-1]

    # Same tool, different intent
    intent_config2 = config.model_copy(update={
        "delegation_id": "del-intent",
        "intent_resolver": lambda tool, args: f"Check KYC for fraud investigation",
    })
    intent_mw2 = NuggetsAuthorityMiddleware(intent_config2)

    request = make_tool_request("check_kyc_status", {"target": "kyc_service", "user_id": "u-123"})
    handler = make_handler('{"verified": true}')
    intent_mw2.wrap_tool_call(request, handler)
    proof2 = intent_mw2.proofs[-1]

    print(f"  Intent 1: 'compliance review'")
    print(f"    hash:  {proof1.intent_hash}")
    print(f"  Intent 2: 'fraud investigation'")
    print(f"    hash:  {proof2.intent_hash}")
    print(f"  Same tool, same params, different intent:")
    print(f"    Hashes match? {proof1.intent_hash == proof2.intent_hash}")
    assert proof1.intent_hash != proof2.intent_hash, "Intent binding failed!"
    print(f"    ✓ Different intent → different proof hash")

    # --- Scenario 7: Proof verification ---
    banner("Scenario 7: Independent proof verification")
    proof_to_verify = proof1
    proof_json = proof_to_verify.model_dump()

    # Export proof
    proof_path = Path(__file__).parent / "demo_proof.json"
    with open(proof_path, "w") as f:
        json.dump(proof_json, f, indent=2)
    print(f"  Proof exported to: {proof_path.name}")

    # Verify independently
    verification = verify_proof(proof_json)
    print(f"\n  Independent Verification:")
    print(f"    Signature valid:  {verification['valid']}")
    print(f"    Who acted:        {verification['who_acted']}")
    print(f"    Authority:        {verification['under_whose_authority']}")
    print(f"    Constraints:      {verification['what_constraints']}")
    print(f"    Intent hash:      {verification['with_what_intent'][:16]}...")
    print(f"    Timestamp:        {verification['at_what_time']}")

    # --- Summary ---
    banner("Demo Summary")
    all_proofs = middleware.proofs + revoke_mw.proofs + intent_mw.proofs + intent_mw2.proofs
    print(f"  Total proofs emitted:  {len(all_proofs)}")
    print(f"  Audit log entries:     {len(get_audit_log())}")
    print()
    print("  Demonstrated:")
    print("    ✓ Actor Identity      — agent DID in all proofs")
    print("    ✓ Delegated Authority — scoped delegation enforced")
    print("    ✓ Policy/Constraints  — tool, target, cap, expiry, revocation")
    print("    ✓ Intent Binding      — different intent = different hash")
    print("    ✓ Consent             — revocation immediately blocked")
    print("    ✓ Accountability      — portable proof verified independently")
    print()
    print("  Cross-boundary:")
    print(f"    Delegation issued by: {ORG_A['name']}")
    print(f"    Agent running in:     {ORG_B['name']}")
    print(f"    Tool targeting:       kyc_service")
    print(f"    Proof verified by:    independent verifier (no runtime needed)")
    print()


if __name__ == "__main__":
    run()
