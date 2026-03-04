"""Tests for NuggetsAuthorityMiddleware."""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import ToolMessage

from langchain_nuggets.middleware.authority_middleware import NuggetsAuthorityMiddleware
from langchain_nuggets.middleware.proof import hash_intent, hash_parameters
from langchain_nuggets.middleware.types import MiddlewareConfig


@pytest.fixture
def config():
    return MiddlewareConfig(
        api_url="https://api.nuggets.test",
        partner_id="partner-123",
        partner_secret="secret-456",
        agent_id="agent-123",
        controller_id="org-456",
        delegation_id="del-789",
    )


@pytest.fixture
def allow_response():
    return {
        "decision": "ALLOW",
        "proof_id": "proof-xyz",
        "signature": "sig-abc",
        "reason_code": None,
        "constraints_evaluated": ["tool_allowed", "target_allowed", "cap_remaining"],
    }


@pytest.fixture
def deny_response():
    return {
        "decision": "DENY",
        "proof_id": "proof-xyz",
        "signature": "sig-abc",
        "reason_code": "POLICY_VIOLATION",
    }


@pytest.fixture
def mock_request():
    request = MagicMock()
    request.tool_call = {
        "name": "external_api_call",
        "args": {"target": "stripe", "amount": 100},
        "id": "call-123",
    }
    return request


@pytest.fixture
def mock_handler():
    handler = MagicMock()
    handler.return_value = ToolMessage(
        content='{"status": "success", "id": "txn-456"}',
        tool_call_id="call-123",
    )
    return handler


@pytest.fixture
def mock_async_handler():
    handler = AsyncMock()
    handler.return_value = ToolMessage(
        content='{"status": "success", "id": "txn-456"}',
        tool_call_id="call-123",
    )
    return handler


class TestConstruction:
    def test_create_middleware(self, config):
        middleware = NuggetsAuthorityMiddleware(config)
        assert middleware is not None

    def test_proofs_initially_empty(self, config):
        middleware = NuggetsAuthorityMiddleware(config)
        assert middleware.proofs == []


class TestSyncWrapToolCall:
    def test_allow_executes_tool(self, config, allow_response, mock_request, mock_handler):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.post.return_value = allow_response

        result = middleware.wrap_tool_call(mock_request, mock_handler)

        mock_handler.assert_called_once_with(mock_request)
        assert isinstance(result, ToolMessage)
        assert "success" in result.content

    def test_allow_emits_proof(self, config, allow_response, mock_request, mock_handler):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.post.return_value = allow_response

        middleware.wrap_tool_call(mock_request, mock_handler)

        assert len(middleware.proofs) == 1
        proof = middleware.proofs[0]
        assert proof.proof_id == "proof-xyz"
        assert proof.agent_id == "agent-123"
        assert proof.tool == "external_api_call"
        assert proof.authority_signature == "sig-abc"

    def test_deny_blocks_tool(self, config, deny_response, mock_request, mock_handler):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.post.return_value = deny_response

        result = middleware.wrap_tool_call(mock_request, mock_handler)

        mock_handler.assert_not_called()
        assert isinstance(result, ToolMessage)
        data = json.loads(result.content)
        assert data["status"] == "DENIED"
        assert data["tool"] == "external_api_call"

    def test_deny_includes_reason(self, config, deny_response, mock_request, mock_handler):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.post.return_value = deny_response

        result = middleware.wrap_tool_call(mock_request, mock_handler)

        data = json.loads(result.content)
        assert data["reason_code"] == "POLICY_VIOLATION"

    def test_error_fails_closed(self, config, mock_request, mock_handler):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.post.side_effect = ConnectionError("Network error")

        result = middleware.wrap_tool_call(mock_request, mock_handler)

        mock_handler.assert_not_called()
        assert isinstance(result, ToolMessage)
        data = json.loads(result.content)
        assert data["status"] == "ERROR"
        assert "Network error" in data["message"]

    def test_proof_callback_invoked(self, config, allow_response, mock_request, mock_handler):
        callback = MagicMock()
        config_with_cb = config.model_copy(update={"on_proof": callback})
        middleware = NuggetsAuthorityMiddleware(config_with_cb)
        middleware._client = MagicMock()
        middleware._client.post.return_value = allow_response

        middleware.wrap_tool_call(mock_request, mock_handler)

        callback.assert_called_once()
        proof = callback.call_args[0][0]
        assert proof.proof_id == "proof-xyz"

    def test_parameters_hash_in_eval_request(self, config, allow_response, mock_request, mock_handler):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.post.return_value = allow_response

        middleware.wrap_tool_call(mock_request, mock_handler)

        call_args = middleware._client.post.call_args
        payload = call_args[0][1]
        expected_hash = hash_parameters({"target": "stripe", "amount": 100})
        assert payload["action"]["parameters_hash"] == expected_hash

    def test_multiple_calls_accumulate_proofs(self, config, allow_response, mock_request, mock_handler):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.post.return_value = allow_response

        middleware.wrap_tool_call(mock_request, mock_handler)
        middleware.wrap_tool_call(mock_request, mock_handler)
        middleware.wrap_tool_call(mock_request, mock_handler)

        assert len(middleware.proofs) == 3

    def test_latency_tracking(self, config, allow_response, mock_request, mock_handler):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.post.return_value = allow_response

        middleware.wrap_tool_call(mock_request, mock_handler)

        proof = middleware.proofs[0]
        assert proof.latency_ms > 0


class TestAsyncWrapToolCall:
    async def test_allow_executes_tool(
        self, config, allow_response, mock_request, mock_async_handler
    ):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.apost = AsyncMock(return_value=allow_response)

        result = await middleware.awrap_tool_call(mock_request, mock_async_handler)

        mock_async_handler.assert_awaited_once_with(mock_request)
        assert isinstance(result, ToolMessage)
        assert "success" in result.content

    async def test_deny_blocks_tool(
        self, config, deny_response, mock_request, mock_async_handler
    ):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.apost = AsyncMock(return_value=deny_response)

        result = await middleware.awrap_tool_call(mock_request, mock_async_handler)

        mock_async_handler.assert_not_awaited()
        data = json.loads(result.content)
        assert data["status"] == "DENIED"

    async def test_error_fails_closed(self, config, mock_request, mock_async_handler):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.apost = AsyncMock(side_effect=ConnectionError("Network error"))

        result = await middleware.awrap_tool_call(mock_request, mock_async_handler)

        mock_async_handler.assert_not_awaited()
        data = json.loads(result.content)
        assert data["status"] == "ERROR"

    async def test_allow_emits_proof(
        self, config, allow_response, mock_request, mock_async_handler
    ):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.apost = AsyncMock(return_value=allow_response)

        await middleware.awrap_tool_call(mock_request, mock_async_handler)

        assert len(middleware.proofs) == 1
        assert middleware.proofs[0].proof_id == "proof-xyz"


class TestMiddlewareTls:
    def test_threads_tls_to_client(self):
        config = MiddlewareConfig(
            api_url="https://api.test",
            partner_id="p",
            partner_secret="s",
            agent_id="a",
            controller_id="c",
            delegation_id="d",
            ca_cert="/path/ca.pem",
        )
        middleware = NuggetsAuthorityMiddleware(config)
        assert middleware._client._verify == "/path/ca.pem"


class TestIntentBinding:
    def test_intent_hash_in_proof_when_intent_resolver_set(
        self, config, allow_response, mock_request, mock_handler
    ):
        config_with_intent = config.model_copy(
            update={"intent_resolver": lambda tool, args: "transfer funds to user"}
        )
        middleware = NuggetsAuthorityMiddleware(config_with_intent)
        middleware._client = MagicMock()
        middleware._client.post.return_value = allow_response

        middleware.wrap_tool_call(mock_request, mock_handler)

        proof = middleware.proofs[0]
        assert proof.intent_hash is not None
        assert len(proof.intent_hash) == 64  # SHA-256 hex

    def test_no_intent_hash_without_resolver(
        self, config, allow_response, mock_request, mock_handler
    ):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.post.return_value = allow_response

        middleware.wrap_tool_call(mock_request, mock_handler)

        proof = middleware.proofs[0]
        assert proof.intent_hash is None

    def test_different_intent_different_proof_hash(
        self, config, allow_response, mock_request, mock_handler
    ):
        """Same tool + same args + different intent → different intent_hash in proof."""
        intents = iter(["transfer funds", "check balance"])
        config_with_intent = config.model_copy(
            update={"intent_resolver": lambda tool, args: next(intents)}
        )
        middleware = NuggetsAuthorityMiddleware(config_with_intent)
        middleware._client = MagicMock()
        middleware._client.post.return_value = allow_response

        middleware.wrap_tool_call(mock_request, mock_handler)
        middleware.wrap_tool_call(mock_request, mock_handler)

        proof1, proof2 = middleware.proofs
        assert proof1.intent_hash != proof2.intent_hash

    def test_intent_hash_sent_in_eval_request(
        self, config, allow_response, mock_request, mock_handler
    ):
        config_with_intent = config.model_copy(
            update={"intent_resolver": lambda tool, args: "transfer funds"}
        )
        middleware = NuggetsAuthorityMiddleware(config_with_intent)
        middleware._client = MagicMock()
        middleware._client.post.return_value = allow_response

        middleware.wrap_tool_call(mock_request, mock_handler)

        payload = middleware._client.post.call_args[0][1]
        assert payload["action"]["intent_hash"] is not None
        assert payload["action"]["intent"] == "transfer funds"


class TestConstraintsEvaluated:
    def test_constraints_in_proof(
        self, config, allow_response, mock_request, mock_handler
    ):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.post.return_value = allow_response

        middleware.wrap_tool_call(mock_request, mock_handler)

        proof = middleware.proofs[0]
        assert proof.constraints_evaluated == ["tool_allowed", "target_allowed", "cap_remaining"]

    def test_empty_constraints_when_not_provided(
        self, config, mock_request, mock_handler
    ):
        response_no_constraints = {
            "decision": "ALLOW",
            "proof_id": "proof-xyz",
            "signature": "sig-abc",
            "reason_code": None,
        }
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.post.return_value = response_no_constraints

        middleware.wrap_tool_call(mock_request, mock_handler)

        proof = middleware.proofs[0]
        assert proof.constraints_evaluated == []

    async def test_constraints_in_async_proof(
        self, config, allow_response, mock_request, mock_async_handler
    ):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.apost = AsyncMock(return_value=allow_response)

        await middleware.awrap_tool_call(mock_request, mock_async_handler)

        proof = middleware.proofs[0]
        assert proof.constraints_evaluated == ["tool_allowed", "target_allowed", "cap_remaining"]
