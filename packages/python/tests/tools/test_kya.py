import json
from unittest.mock import patch, AsyncMock

import pytest

from langchain_nuggets.client.nuggets_api_client import NuggetsApiClient
from langchain_nuggets.tools.kya import (
    RegisterAgentIdentity,
    VerifyAgentIdentity,
    GetAgentTrustScore,
)

TEST_CONFIG = {
    "api_url": "https://api.nuggets.test",
    "partner_id": "test-partner",
    "partner_secret": "test-secret",
}


def make_client():
    return NuggetsApiClient(TEST_CONFIG)


class TestRegisterAgentIdentity:
    def test_name_and_description(self):
        tool = RegisterAgentIdentity(client=make_client())
        assert tool.name == "register_agent_identity"
        assert "agent" in tool.description

    def test_invoke_calls_post(self):
        client = make_client()
        tool = RegisterAgentIdentity(client=client)
        mock_identity = {
            "agentId": "agent-123",
            "did": "did:nuggets:agent-123",
            "provenance": {"github": "https://github.com/test-dev"},
            "registeredAt": "2024-06-01T00:00:00Z",
        }
        with patch.object(client, "post", return_value=mock_identity) as mock_post:
            result = tool.invoke({"agentName": "TestAgent", "githubUrl": "https://github.com/test-dev"})
            parsed = json.loads(result)
            assert parsed == mock_identity
            mock_post.assert_called_once_with("/kya/agents", {"agentName": "TestAgent", "githubUrl": "https://github.com/test-dev"})

    def test_invoke_without_optional_fields(self):
        client = make_client()
        tool = RegisterAgentIdentity(client=client)
        mock_identity = {
            "agentId": "agent-456",
            "did": "did:nuggets:agent-456",
            "provenance": {},
            "registeredAt": "2024-06-01T00:00:00Z",
        }
        with patch.object(client, "post", return_value=mock_identity) as mock_post:
            result = tool.invoke({"agentName": "MinimalAgent"})
            parsed = json.loads(result)
            assert parsed == mock_identity
            mock_post.assert_called_once_with("/kya/agents", {"agentName": "MinimalAgent"})


class TestVerifyAgentIdentity:
    def test_name_and_description(self):
        tool = VerifyAgentIdentity(client=make_client())
        assert tool.name == "verify_agent_identity"
        assert "agent" in tool.description

    def test_invoke_calls_get(self):
        client = make_client()
        tool = VerifyAgentIdentity(client=client)
        mock_identity = {
            "agentId": "agent-456",
            "did": "did:nuggets:agent-456",
            "provenance": {"github": "https://github.com/other-dev", "twitter": "@otherdev"},
            "registeredAt": "2024-05-15T00:00:00Z",
        }
        with patch.object(client, "get", return_value=mock_identity) as mock_get:
            result = tool.invoke({"agentId": "agent-456"})
            parsed = json.loads(result)
            assert parsed == mock_identity
            mock_get.assert_called_once_with("/kya/agents/agent-456")


class TestGetAgentTrustScore:
    def test_name_and_description(self):
        tool = GetAgentTrustScore(client=make_client())
        assert tool.name == "get_agent_trust_score"
        assert "agent" in tool.description

    def test_invoke_calls_get(self):
        client = make_client()
        tool = GetAgentTrustScore(client=client)
        mock_score = {
            "agentId": "agent-456",
            "score": 0.85,
            "signals": {"githubVerified": True, "socialVerified": True, "registrationAge": 180},
        }
        with patch.object(client, "get", return_value=mock_score) as mock_get:
            result = tool.invoke({"agentId": "agent-456"})
            parsed = json.loads(result)
            assert parsed == mock_score
            assert parsed["score"] == 0.85
            assert parsed["signals"]["githubVerified"] is True
            mock_get.assert_called_once_with("/kya/agents/agent-456/trust-score")
