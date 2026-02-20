"""Tests for the NuggetsAuth LangGraph provider."""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langgraph_sdk import Auth
from langgraph_sdk.auth.exceptions import HTTPException

from langchain_nuggets.langgraph.auth import NuggetsAuth
from langchain_nuggets.langgraph.token_verifier import NuggetsAuthError


@pytest.fixture
def mock_verifier():
    """Mock the NuggetsTokenVerifier to avoid real OIDC calls."""
    with patch("langchain_nuggets.langgraph.auth.NuggetsTokenVerifier") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.verify_token = AsyncMock(
            return_value={
                "sub": "user-123",
                "email": "alice@example.com",
                "name": "Alice",
                "scope": "openid email profile",
            }
        )
        mock_cls.return_value = mock_instance
        yield mock_instance


def test_create_with_explicit_config(mock_verifier):
    nuggets = NuggetsAuth(issuer_url="https://oidc.nuggets.test")
    assert nuggets.auth is not None
    assert isinstance(nuggets.auth, Auth)


def test_create_with_env_vars(mock_verifier):
    with patch.dict(os.environ, {"NUGGETS_OIDC_ISSUER_URL": "https://oidc.nuggets.test"}):
        nuggets = NuggetsAuth()
        assert isinstance(nuggets.auth, Auth)


def test_raises_without_issuer():
    with patch.dict(os.environ, {}, clear=True):
        # Remove the key if it exists
        os.environ.pop("NUGGETS_OIDC_ISSUER_URL", None)
        with pytest.raises(ValueError, match="issuer_url"):
            NuggetsAuth()


@pytest.mark.asyncio
async def test_authenticate_valid_token(mock_verifier):
    nuggets = NuggetsAuth(issuer_url="https://oidc.nuggets.test")

    result = await nuggets._authenticate(authorization="Bearer valid-token")

    assert result["identity"] == "user-123"
    assert result["is_authenticated"] is True
    assert result["email"] == "alice@example.com"
    assert "openid" in result["permissions"]
    mock_verifier.verify_token.assert_called_once_with("valid-token")


@pytest.mark.asyncio
async def test_authenticate_missing_header(mock_verifier):
    nuggets = NuggetsAuth(issuer_url="https://oidc.nuggets.test")

    with pytest.raises(HTTPException) as exc_info:
        await nuggets._authenticate(authorization=None)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_authenticate_invalid_token(mock_verifier):
    mock_verifier.verify_token = AsyncMock(
        side_effect=NuggetsAuthError("Invalid token", 401)
    )

    nuggets = NuggetsAuth(issuer_url="https://oidc.nuggets.test")

    with pytest.raises(HTTPException) as exc_info:
        await nuggets._authenticate(authorization="Bearer bad-token")

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_authenticate_with_kyc_enrichment(mock_verifier):
    with patch("langchain_nuggets.langgraph.auth.NuggetsApiClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.aget = AsyncMock(
            return_value={"kyc_verified": True, "user_id": "user-123"}
        )
        mock_client_cls.return_value = mock_client

        nuggets = NuggetsAuth(
            issuer_url="https://oidc.nuggets.test",
            api_url="https://api.nuggets.test",
            partner_id="pid",
            partner_secret="psecret",
        )

        result = await nuggets._authenticate(authorization="Bearer valid-token")

        assert result["kyc_verified"] is True
        mock_client.aget.assert_called_once_with("/auth/status/user-123")


def test_auth_property_returns_auth_object(mock_verifier):
    nuggets = NuggetsAuth(issuer_url="https://oidc.nuggets.test")
    auth = nuggets.auth
    assert isinstance(auth, Auth)
    # Verify the authenticate handler was registered
    assert auth._authenticate_handler is not None


class TestNuggetsAuthTls:
    def test_threads_tls_to_verifier(self):
        with patch.dict(os.environ, {}, clear=True):
            auth = NuggetsAuth(
                issuer_url="https://oidc.test",
                ca_cert="/path/ca.pem",
                verify_ssl=True,
            )
            assert auth._verifier._verify == "/path/ca.pem"

    def test_threads_tls_to_api_client(self):
        with patch.dict(os.environ, {}, clear=True):
            auth = NuggetsAuth(
                issuer_url="https://oidc.test",
                api_url="https://api.test",
                partner_id="pid",
                partner_secret="psec",
                ca_cert="/path/ca.pem",
                verify_ssl=False,
            )
            assert auth._api_client._verify is False
