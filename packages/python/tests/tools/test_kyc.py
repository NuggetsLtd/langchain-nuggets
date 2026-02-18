import json
from unittest.mock import patch, AsyncMock

import pytest

from langchain_nuggets.client.nuggets_api_client import NuggetsApiClient
from langchain_nuggets.tools.kyc import (
    InitiateKycVerification,
    CheckKycStatus,
    VerifyAge,
    VerifyCredential,
)

TEST_CONFIG = {
    "api_url": "https://api.nuggets.test",
    "partner_id": "test-partner",
    "partner_secret": "test-secret",
}


def make_client():
    return NuggetsApiClient(TEST_CONFIG)


class TestInitiateKycVerification:
    def test_name_and_description(self):
        tool = InitiateKycVerification(client=make_client())
        assert tool.name == "initiate_kyc_verification"
        assert "KYC" in tool.description
        assert "verification" in tool.description

    def test_invoke_calls_post(self):
        client = make_client()
        tool = InitiateKycVerification(client=client)
        mock_session = {
            "sessionId": "sess-123",
            "deeplink": "nuggets://kyc/sess-123",
            "qrCodeUrl": "https://api.nuggets.test/qr/sess-123",
        }
        with patch.object(client, "post", return_value=mock_session) as mock_post:
            result = tool.invoke({"userId": "user@example.com"})
            parsed = json.loads(result)
            assert parsed == mock_session
            mock_post.assert_called_once_with("/kyc/sessions", {"userId": "user@example.com"})

    @pytest.mark.asyncio
    async def test_ainvoke_calls_apost(self):
        client = make_client()
        tool = InitiateKycVerification(client=client)
        mock_session = {
            "sessionId": "sess-123",
            "deeplink": "nuggets://kyc/sess-123",
            "qrCodeUrl": "https://api.nuggets.test/qr/sess-123",
        }
        with patch.object(client, "apost", new_callable=AsyncMock, return_value=mock_session) as mock_apost:
            result = await tool.ainvoke({"userId": "user@example.com"})
            parsed = json.loads(result)
            assert parsed == mock_session
            mock_apost.assert_called_once_with("/kyc/sessions", {"userId": "user@example.com"})


class TestCheckKycStatus:
    def test_name_and_description(self):
        tool = CheckKycStatus(client=make_client())
        assert tool.name == "check_kyc_status"
        assert "status" in tool.description
        assert "KYC" in tool.description

    def test_invoke_calls_get(self):
        client = make_client()
        tool = CheckKycStatus(client=client)
        mock_result = {
            "sessionId": "sess-123",
            "status": "completed",
            "credentials": [
                {
                    "id": "cred-1",
                    "type": ["VerifiableCredential", "IdentityCredential"],
                    "issuer": "did:nuggets:issuer",
                    "issuanceDate": "2024-01-01T00:00:00Z",
                    "credentialSubject": {"name": "Test User"},
                }
            ],
        }
        with patch.object(client, "get", return_value=mock_result) as mock_get:
            result = tool.invoke({"sessionId": "sess-123"})
            parsed = json.loads(result)
            assert parsed == mock_result
            mock_get.assert_called_once_with("/kyc/sessions/sess-123")


class TestVerifyAge:
    def test_name_and_description(self):
        tool = VerifyAge(client=make_client())
        assert tool.name == "verify_age"
        assert "age" in tool.description

    def test_invoke_calls_post(self):
        client = make_client()
        tool = VerifyAge(client=client)
        mock_session = {
            "sessionId": "age-sess-456",
            "deeplink": "nuggets://kyc/age-sess-456",
            "qrCodeUrl": "https://api.nuggets.test/qr/age-sess-456",
        }
        with patch.object(client, "post", return_value=mock_session) as mock_post:
            result = tool.invoke({"userId": "user@example.com", "minimumAge": 18})
            parsed = json.loads(result)
            assert parsed == mock_session
            mock_post.assert_called_once_with("/kyc/verify-age", {"userId": "user@example.com", "minimumAge": 18})


class TestVerifyCredential:
    def test_name_and_description(self):
        tool = VerifyCredential(client=make_client())
        assert tool.name == "verify_credential"
        assert "credential" in tool.description

    def test_invoke_calls_post(self):
        client = make_client()
        tool = VerifyCredential(client=client)
        mock_session = {
            "sessionId": "cred-sess-789",
            "deeplink": "nuggets://kyc/cred-sess-789",
            "qrCodeUrl": "https://api.nuggets.test/qr/cred-sess-789",
        }
        with patch.object(client, "post", return_value=mock_session) as mock_post:
            result = tool.invoke({"userId": "user@example.com", "credentialType": "address"})
            parsed = json.loads(result)
            assert parsed == mock_session
            mock_post.assert_called_once_with("/kyc/verify-credential", {"userId": "user@example.com", "credentialType": "address"})
