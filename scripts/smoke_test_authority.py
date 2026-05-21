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
    export NUGGETS_AUTHORITY_URL="https://accounts-dev.internal-nuggets.life"
    export NUGGETS_OIDC_ISSUER_URL="https://auth-dev.internal-nuggets.life"
    export NUGGETS_AGENT_ID="did:web:auth-dev.internal-nuggets.life:..."
    export NUGGETS_CONTROLLER_ID="did:nuggets:oidc:..."
    export NUGGETS_DELEGATION_ID="42"
    export NUGGETS_AGENT_PRIVATE_KEY="/path/to/agent-jwks.json"  # or PEM
    export NUGGETS_TOOL="your_tool_name"    # any capability in the delegation's allowed_capabilities
    export NUGGETS_TARGET="your_target"     # optional; must match the
                                            # delegation's allowed_targets when set

    python scripts/smoke_test_authority.py
"""
from __future__ import annotations

import json
import os
import sys
from types import SimpleNamespace
from typing import Any, Dict, Union

from langchain_core.messages import ToolMessage

from langchain_nuggets.middleware import MiddlewareConfig, NuggetsAuthorityMiddleware

REQUIRED_ENV = [
    "NUGGETS_AUTHORITY_URL",
    "NUGGETS_OIDC_ISSUER_URL",
    "NUGGETS_AGENT_ID",
    "NUGGETS_CONTROLLER_ID",
    "NUGGETS_DELEGATION_ID",
    "NUGGETS_AGENT_PRIVATE_KEY",
]


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    sys.exit(1)


def load_key_from_env() -> Union[str, Dict[str, Any]]:
    """Resolve NUGGETS_AGENT_PRIVATE_KEY to a value MiddlewareConfig accepts.

    A file path (PEM, JWK JSON, JWKS JSON) is handed off as-is to the
    middleware loader, which handles all three forms. Inline JSON is
    parsed and passed as a dict so MiddlewareConfig validation runs
    against a structured value rather than a raw string.
    """
    raw = os.environ["NUGGETS_AGENT_PRIVATE_KEY"]
    if raw.lstrip().startswith("{"):
        return json.loads(raw)
    return raw


def main() -> None:
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        fail(f"missing env vars: {', '.join(missing)}")

    tool_name = os.environ.get("NUGGETS_TOOL")
    if not tool_name:
        fail("NUGGETS_TOOL must be set to a capability listed in the delegation")

    config = MiddlewareConfig(
        api_url=os.environ["NUGGETS_AUTHORITY_URL"],
        oidc_issuer_url=os.environ["NUGGETS_OIDC_ISSUER_URL"],
        agent_id=os.environ["NUGGETS_AGENT_ID"],
        controller_id=os.environ["NUGGETS_CONTROLLER_ID"],
        delegation_id=os.environ["NUGGETS_DELEGATION_ID"],
        agent_private_key=load_key_from_env(),
    )

    middleware = NuggetsAuthorityMiddleware(config)

    target = os.environ.get("NUGGETS_TARGET")
    args: Dict[str, Any] = {"userId": "smoke-test-user"}
    if target:
        args["target"] = target

    request = SimpleNamespace(
        tool_call={
            "name": tool_name,
            "args": args,
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
