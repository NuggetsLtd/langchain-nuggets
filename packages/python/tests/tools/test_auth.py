import json
from unittest.mock import patch, AsyncMock

import pytest

from langchain_nuggets.client.nuggets_api_client import NuggetsApiClient
from langchain_nuggets.tools.auth import (
    RequestCredentialPresentation,
    VerifyPresentation,
    InitiateOAuthFlow,
    CheckAuthStatus,
)

TEST_CONFIG = {
    "api_url": "https://api.nuggets.test",
    "partner_id": "test-partner",
    "partner_secret": "test-secret",
}


def make_client():
    return NuggetsApiClient(TEST_CONFIG)


class TestRequestCredentialPresentation:
    def test_name_and_description(self):
        tool = RequestCredentialPresentation(client=make_client())
        assert tool.name == "request_credential_presentation"
        assert "credential" in tool.description
        assert "present" in tool.description

    def test_invoke_calls_post(self):
        client = make_client()
        tool = RequestCredentialPresentation(client=client)
        mock_presentation = {
            "sessionId": "pres-123",
            "deeplink": "nuggets://present/pres-123",
            "qrCodeUrl": "https://api.nuggets.test/qr/pres-123",
        }
        with patch.object(client, "post", return_value=mock_presentation) as mock_post:
            result = tool.invoke({"userId": "user@example.com", "credentialTypes": ["email", "phone", "address"]})
            parsed = json.loads(result)
            assert parsed == mock_presentation
            mock_post.assert_called_once_with("/credentials/presentations", {"userId": "user@example.com", "credentialTypes": ["email", "phone", "address"]})


class TestVerifyPresentation:
    def test_name_and_description(self):
        tool = VerifyPresentation(client=make_client())
        assert tool.name == "verify_presentation"
        assert "credential" in tool.description
        assert "presentation" in tool.description

    def test_invoke_calls_get(self):
        client = make_client()
        tool = VerifyPresentation(client=client)
        mock_result = {
            "sessionId": "pres-123",
            "status": "presented",
            "credentials": [
                {
                    "id": "cred-1",
                    "type": ["VerifiableCredential", "EmailCredential"],
                    "issuer": "did:nuggets:issuer",
                    "issuanceDate": "2024-01-01T00:00:00Z",
                    "credentialSubject": {"email": "user@example.com"},
                }
            ],
            "verified": True,
        }
        with patch.object(client, "get", return_value=mock_result) as mock_get:
            result = tool.invoke({"sessionId": "pres-123"})
            parsed = json.loads(result)
            assert parsed == mock_result
            assert parsed["verified"] is True
            assert parsed["status"] == "presented"
            mock_get.assert_called_once_with("/credentials/presentations/pres-123")


class TestInitiateOAuthFlow:
    def test_name_and_description(self):
        tool = InitiateOAuthFlow(client=make_client())
        assert tool.name == "initiate_oauth_flow"
        assert "OAuth" in tool.description
        assert "authentication" in tool.description

    def test_invoke_calls_post_with_scopes(self):
        client = make_client()
        tool = InitiateOAuthFlow(client=client)
        mock_session = {
            "authorizationUrl": "https://auth.nuggets.test/authorize?state=abc",
            "state": "abc",
            "codeVerifier": "verifier-123",
        }
        with patch.object(client, "post", return_value=mock_session) as mock_post:
            result = tool.invoke({"redirectUri": "https://myapp.test/callback", "scopes": ["openid", "profile", "email"]})
            parsed = json.loads(result)
            assert parsed == mock_session
            assert parsed["authorizationUrl"] is not None
            mock_post.assert_called_once_with("/oauth/authorize", {"redirectUri": "https://myapp.test/callback", "scopes": ["openid", "profile", "email"]})

    def test_invoke_defaults_scopes_to_openid(self):
        client = make_client()
        tool = InitiateOAuthFlow(client=client)
        mock_session = {
            "authorizationUrl": "https://auth.nuggets.test/authorize?state=def",
            "state": "def",
            "codeVerifier": "verifier-456",
        }
        with patch.object(client, "post", return_value=mock_session) as mock_post:
            result = tool.invoke({"redirectUri": "https://myapp.test/callback"})
            parsed = json.loads(result)
            assert parsed == mock_session
            mock_post.assert_called_once_with("/oauth/authorize", {"redirectUri": "https://myapp.test/callback", "scopes": ["openid"]})

    @pytest.mark.asyncio
    async def test_ainvoke_defaults_scopes_to_openid(self):
        client = make_client()
        tool = InitiateOAuthFlow(client=client)
        mock_session = {
            "authorizationUrl": "https://auth.nuggets.test/authorize?state=ghi",
            "state": "ghi",
            "codeVerifier": "verifier-789",
        }
        with patch.object(client, "apost", new_callable=AsyncMock, return_value=mock_session) as mock_apost:
            result = await tool.ainvoke({"redirectUri": "https://myapp.test/callback"})
            parsed = json.loads(result)
            assert parsed == mock_session
            mock_apost.assert_called_once_with("/oauth/authorize", {"redirectUri": "https://myapp.test/callback", "scopes": ["openid"]})


class TestCheckAuthStatus:
    def test_name_and_description(self):
        tool = CheckAuthStatus(client=make_client())
        assert tool.name == "check_auth_status"
        assert "authenticated" in tool.description
        assert "verification" in tool.description

    def test_invoke_calls_get(self):
        client = make_client()
        tool = CheckAuthStatus(client=client)
        mock_status = {
            "authenticated": True,
            "userId": "user@example.com",
            "kycVerified": True,
            "credentials": ["email", "phone", "address"],
        }
        with patch.object(client, "get", return_value=mock_status) as mock_get:
            result = tool.invoke({"userId": "user@example.com"})
            parsed = json.loads(result)
            assert parsed == mock_status
            assert parsed["authenticated"] is True
            assert parsed["kycVerified"] is True
            mock_get.assert_called_once_with("/auth/status/user@example.com")
