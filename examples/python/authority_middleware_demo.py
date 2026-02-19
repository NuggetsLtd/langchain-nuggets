"""Demo: NuggetsAuthorityMiddleware — Pre-execution authority enforcement.

This demo shows how NuggetsAuthorityMiddleware intercepts tool calls,
validates authority with the Nuggets control plane, and emits proof artifacts.

The demo mocks the Nuggets API to run standalone. In production, the
middleware calls a live authority evaluation endpoint.

Usage:
    python examples/python/authority_middleware_demo.py
"""
from __future__ import annotations

import json
import time
from unittest.mock import MagicMock

from langchain_core.messages import ToolMessage

from langchain_nuggets.middleware import (
    MiddlewareConfig,
    NuggetsAuthorityMiddleware,
    ProofArtifact,
)


def main() -> None:
    # --- Setup ---
    collected_proofs: list[ProofArtifact] = []

    config = MiddlewareConfig(
        api_url="https://api.nuggets.example",
        partner_id="partner-demo",
        partner_secret="secret-demo",
        agent_id="agent-demo-001",
        controller_id="org-acme",
        delegation_id="del-finance-2026",
        on_proof=lambda proof: collected_proofs.append(proof),
    )

    middleware = NuggetsAuthorityMiddleware(config)

    # --- Scenario 1: ALLOW ---
    print("=" * 60)
    print("Scenario 1: Tool execution ALLOWED")
    print("=" * 60)

    # Mock the API client to return ALLOW
    middleware._client = MagicMock()
    middleware._client.post.return_value = {
        "decision": "ALLOW",
        "proof_id": "proof-001",
        "signature": "sig-abc123",
        "reason_code": None,
    }

    # Simulate a tool call request
    request = MagicMock()
    request.tool_call = {
        "name": "stripe_payment",
        "args": {"amount": 250.00, "currency": "USD", "recipient": "supplier-42"},
        "id": "call-001",
    }

    # Simulate the actual tool handler
    def mock_handler(req: object) -> ToolMessage:
        time.sleep(0.01)  # Simulate tool execution
        return ToolMessage(
            content=json.dumps({"status": "success", "txn_id": "txn-789"}),
            tool_call_id="call-001",
        )

    result = middleware.wrap_tool_call(request, mock_handler)

    print(f"  Tool: stripe_payment")
    print(f"  Decision: ALLOW")
    print(f"  Result: {result.content}")
    proof = middleware.proofs[-1]
    print(f"  Proof ID: {proof.proof_id}")
    print(f"  Signature: {proof.authority_signature}")
    print(f"  Latency: {proof.latency_ms:.1f}ms")
    print()

    # --- Scenario 2: DENY ---
    print("=" * 60)
    print("Scenario 2: Tool execution DENIED")
    print("=" * 60)

    middleware._client.post.return_value = {
        "decision": "DENY",
        "proof_id": "proof-002",
        "signature": "sig-def456",
        "reason_code": "SCOPE_EXCEEDED",
    }

    request2 = MagicMock()
    request2.tool_call = {
        "name": "delete_database",
        "args": {"database": "production"},
        "id": "call-002",
    }

    handler_not_called = MagicMock()
    result2 = middleware.wrap_tool_call(request2, handler_not_called)

    data = json.loads(result2.content)
    print(f"  Tool: delete_database")
    print(f"  Decision: DENIED")
    print(f"  Reason: {data['reason_code']}")
    print(f"  Handler called: {handler_not_called.called}")
    print()

    # --- Scenario 3: Authority endpoint unreachable (fail closed) ---
    print("=" * 60)
    print("Scenario 3: Authority endpoint ERROR (fail closed)")
    print("=" * 60)

    middleware._client.post.side_effect = ConnectionError("Authority endpoint unreachable")

    request3 = MagicMock()
    request3.tool_call = {
        "name": "send_email",
        "args": {"to": "user@example.com", "body": "Hello"},
        "id": "call-003",
    }

    handler_not_called2 = MagicMock()
    result3 = middleware.wrap_tool_call(request3, handler_not_called2)

    data3 = json.loads(result3.content)
    print(f"  Tool: send_email")
    print(f"  Decision: ERROR (fail closed)")
    print(f"  Message: {data3['message']}")
    print(f"  Handler called: {handler_not_called2.called}")
    print()

    # --- Summary ---
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"  Total proofs emitted: {len(middleware.proofs)}")
    print(f"  Proofs via callback: {len(collected_proofs)}")
    for i, p in enumerate(middleware.proofs):
        print(f"  [{i+1}] proof_id={p.proof_id} tool={p.tool} latency={p.latency_ms:.1f}ms")

    # --- Integration example ---
    print()
    print("=" * 60)
    print("Integration with LangGraph ToolNode")
    print("=" * 60)
    print("""
    from langgraph.prebuilt import ToolNode
    from langchain_nuggets.middleware import NuggetsAuthorityMiddleware, MiddlewareConfig

    config = MiddlewareConfig(
        api_url="https://api.nuggets.life",
        partner_id="your-partner-id",
        partner_secret="your-partner-secret",
        agent_id="agent-001",
        controller_id="org-001",
        delegation_id="del-001",
    )

    middleware = NuggetsAuthorityMiddleware(config)

    # Every tool call goes through Nuggets authority check
    tool_node = ToolNode(
        tools=[your_tool_1, your_tool_2],
        wrap_tool_call=middleware.wrap_tool_call,
    )

    # After execution, inspect proofs
    for proof in middleware.proofs:
        print(f"Proof: {proof.proof_id} for {proof.tool}")
    """)


if __name__ == "__main__":
    main()
