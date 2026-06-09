"""Tests for the AgentMiddleware adapter (langchain create_agent integration)."""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import ToolMessage

# The adapter requires langchain>=1.0 (the [agent] extra). Skip cleanly when
# only langchain-core is installed.
agent_mw_mod = pytest.importorskip("langchain.agents.middleware")
AgentMiddleware = agent_mw_mod.AgentMiddleware

from langchain_nuggets.middleware.agent_middleware import (  # noqa: E402
    NuggetsAuthorityAgentMiddleware,
)
from langchain_nuggets.middleware.types import MiddlewareConfig  # noqa: E402


@pytest.fixture
def test_mode_config():
    return MiddlewareConfig(
        api_url="https://api.nuggets.test",
        agent_id="agent-123",
        controller_id="org-456",
        delegation_id="del-789",
        test_mode=True,
    )


@pytest.fixture
def live_config():
    # Non-test-mode so we can drive a DENY through the inner client. verify_proofs
    # off so we don't need a real discovered JWKS.
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_pem = (
        rsa.generate_private_key(public_exponent=65537, key_size=2048)
        .private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        .decode("utf-8")
    )
    return MiddlewareConfig(
        api_url="https://api.nuggets.test",
        oidc_issuer_url="https://auth.nuggets.test",
        agent_id="agent-123",
        controller_id="org-456",
        delegation_id="del-789",
        agent_private_key=private_pem,
        verify_proofs=False,
    )


@pytest.fixture
def mock_request():
    request = MagicMock()
    request.tool_call = {
        "name": "external_api_call",
        "args": {"target": "stripe", "amount": 100},
        "id": "call-123",
    }
    return request


def test_is_agent_middleware_subclass(test_mode_config):
    mw = NuggetsAuthorityAgentMiddleware(test_mode_config)
    assert isinstance(mw, AgentMiddleware)


def test_exported_from_package_top_level():
    import langchain_nuggets.middleware as pkg

    assert pkg.NuggetsAuthorityAgentMiddleware is NuggetsAuthorityAgentMiddleware


def test_allow_delegates_to_handler(test_mode_config, mock_request):
    mw = NuggetsAuthorityAgentMiddleware(test_mode_config)
    handler = MagicMock(
        return_value=ToolMessage(content='{"ok": true}', tool_call_id="call-123")
    )

    result = mw.wrap_tool_call(mock_request, handler)

    handler.assert_called_once_with(mock_request)
    assert isinstance(result, ToolMessage)
    assert result.content == '{"ok": true}'
    assert len(mw.proofs) == 1


def test_deny_blocks_handler(live_config, mock_request):
    mw = NuggetsAuthorityAgentMiddleware(live_config)
    mw._mw._client = MagicMock()
    mw._mw._client.post.return_value = {
        "decision": "DENY",
        "proof_id": "proof-xyz",
        "signature": "sig-abc",
        "reason_code": "TOOL_NOT_IN_SCOPE",
    }
    handler = MagicMock()

    result = mw.wrap_tool_call(mock_request, handler)

    handler.assert_not_called()
    payload = json.loads(result.content)
    assert payload["status"] == "DENIED"
    assert payload["reason_code"] == "TOOL_NOT_IN_SCOPE"


@pytest.mark.asyncio
async def test_async_allow_delegates(test_mode_config, mock_request):
    mw = NuggetsAuthorityAgentMiddleware(test_mode_config)
    handler = AsyncMock(
        return_value=ToolMessage(content='{"ok": true}', tool_call_id="call-123")
    )

    result = await mw.awrap_tool_call(mock_request, handler)

    handler.assert_awaited_once_with(mock_request)
    assert result.content == '{"ok": true}'
    assert len(mw.proofs) == 1
