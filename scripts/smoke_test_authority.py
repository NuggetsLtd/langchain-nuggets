#!/usr/bin/env python3
"""End-to-end smoke test for NuggetsAuthorityMiddleware against a live backend.

Hits the real Nuggets authority endpoint with one ALLOW-expected tool call
through the middleware. Exits 0 on success, non-zero on failure.

Use against a deployed environment (dev / staging / prod) to confirm the
SDK's request shape, auth flow, and response handling work against the
real Next.js route at /api/authority/evaluate.

Setup:
    Register the agent and download its private key from the accounts portal.
    Pre-create a delegation with NUGGETS_TOOL in its allowed_capabilities;
    note the delegation_id.

Usage:
    export NUGGETS_AUTHORITY_URL="https://accounts-dev.nuggets.life"
    export NUGGETS_PARTNER_ID="..."
    export NUGGETS_PARTNER_SECRET="..."
    export NUGGETS_AGENT_ID="did:nuggets:oidc:..."
    export NUGGETS_CONTROLLER_ID="did:nuggets:oidc:..."
    export NUGGETS_DELEGATION_ID="42"
    export NUGGETS_AGENT_PRIVATE_KEY="/path/to/agent-private-key.pem"
    export NUGGETS_TOOL="check_kyc_status"  # must be in delegation's capabilities

    python scripts/smoke_test_authority.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Union

from langchain_core.messages import ToolMessage

from langchain_nuggets.middleware import MiddlewareConfig, NuggetsAuthorityMiddleware

REQUIRED_ENV = [
    "NUGGETS_AUTHORITY_URL",
    "NUGGETS_PARTNER_ID",
    "NUGGETS_PARTNER_SECRET",
    "NUGGETS_AGENT_ID",
    "NUGGETS_CONTROLLER_ID",
    "NUGGETS_DELEGATION_ID",
    "NUGGETS_AGENT_PRIVATE_KEY",
]


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    sys.exit(1)


def load_key_from_env() -> Union[str, Dict[str, Any]]:
    """Resolve NUGGETS_AGENT_PRIVATE_KEY into a value MiddlewareConfig accepts.

    Supports:
    - Path to a PEM file (`agent.pem`) — returned as-is, SDK reads the file
    - Path to a JWK file (single key dict) — parsed and returned as dict
    - Path to a JWKS file (keys array) — first key returned as dict
    - Inline JSON (JWK or JWKS) — parsed and returned as dict
    """
    raw = os.environ["NUGGETS_AGENT_PRIVATE_KEY"]
    candidate: Any = None

    if raw.lstrip().startswith("{"):
        candidate = json.loads(raw)
    else:
        path = Path(raw)
        if path.is_file():
            content = path.read_text(encoding="utf-8")
            if content.lstrip().startswith("{"):
                candidate = json.loads(content)
            else:
                # Assume PEM; let the SDK read the file by passing the path.
                return raw
        else:
            # Could be an inline PEM string passed directly via env.
            return raw

    if isinstance(candidate, dict) and isinstance(candidate.get("keys"), list):
        if not candidate["keys"]:
            fail("JWKS contained no keys")
        return candidate["keys"][0]
    return candidate


def main() -> None:
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        fail(f"missing env vars: {', '.join(missing)}")

    tool_name = os.environ.get("NUGGETS_TOOL", "check_kyc_status")

    config = MiddlewareConfig(
        api_url=os.environ["NUGGETS_AUTHORITY_URL"],
        partner_id=os.environ["NUGGETS_PARTNER_ID"],
        partner_secret=os.environ["NUGGETS_PARTNER_SECRET"],
        agent_id=os.environ["NUGGETS_AGENT_ID"],
        controller_id=os.environ["NUGGETS_CONTROLLER_ID"],
        delegation_id=os.environ["NUGGETS_DELEGATION_ID"],
        agent_private_key=load_key_from_env(),
    )

    middleware = NuggetsAuthorityMiddleware(config)

    request = SimpleNamespace(
        tool_call={
            "name": tool_name,
            "args": {"userId": "smoke-test-user"},
            "id": "smoke-call-001",
        }
    )

    def handler(_: object) -> ToolMessage:
        return ToolMessage(
            content=json.dumps({"status": "ok", "smoke": True}),
            tool_call_id="smoke-call-001",
        )

    print(f"Calling authority at {config.api_url}{config.authority_endpoint}")
    print(f"  agent_id      = {config.agent_id}")
    print(f"  controller_id = {config.controller_id}")
    print(f"  delegation_id = {config.delegation_id}")
    print(f"  tool          = {tool_name}")

    result = middleware.wrap_tool_call(request, handler)

    if not isinstance(result, ToolMessage):
        fail(f"unexpected result type: {type(result).__name__}")

    try:
        payload = json.loads(result.content)
    except json.JSONDecodeError:
        fail(f"result content not JSON: {result.content!r}")

    if payload.get("status") in {"DENIED", "ERROR"}:
        fail(
            f"decision was {payload['status']} "
            f"(reason: {payload.get('reason_code') or payload.get('message')})"
        )

    if not middleware.proofs:
        fail("no proof artifact emitted")

    proof = middleware.proofs[0]
    print()
    print("OK")
    print("  decision       = ALLOW")
    print(f"  proof_id       = {proof.proof_id}")
    print(f"  signature      = {proof.authority_signature[:32]}...")
    print(f"  latency_ms     = {proof.latency_ms:.1f}")
    print(f"  constraints    = {proof.constraints_evaluated}")


if __name__ == "__main__":
    main()
