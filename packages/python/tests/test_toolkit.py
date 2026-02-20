import os
from unittest.mock import patch

import pytest

from langchain_nuggets import NuggetsToolkit


class TestNuggetsToolkit:
    def test_create_with_explicit_config(self):
        toolkit = NuggetsToolkit(
            api_url="https://api.nuggets.test",
            partner_id="partner-123",
            partner_secret="secret-456",
        )
        tools = toolkit.get_tools()
        assert len(tools) == 11

    def test_create_with_env_vars(self):
        env = {
            "NUGGETS_API_URL": "https://api.nuggets.test",
            "NUGGETS_PARTNER_ID": "partner-123",
            "NUGGETS_PARTNER_SECRET": "secret-456",
        }
        with patch.dict(os.environ, env):
            toolkit = NuggetsToolkit()
            tools = toolkit.get_tools()
            assert len(tools) == 11

    def test_raises_without_config(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="NuggetsToolkit requires"):
                NuggetsToolkit()

    def test_tool_names(self):
        toolkit = NuggetsToolkit(
            api_url="https://api.nuggets.test",
            partner_id="partner-123",
            partner_secret="secret-456",
        )
        tools = toolkit.get_tools()
        names = [t.name for t in tools]
        assert "initiate_kyc_verification" in names
        assert "check_kyc_status" in names
        assert "verify_age" in names
        assert "verify_credential" in names
        assert "register_agent_identity" in names
        assert "verify_agent_identity" in names
        assert "get_agent_trust_score" in names
        assert "request_credential_presentation" in names
        assert "verify_presentation" in names
        assert "initiate_oauth_flow" in names
        assert "check_auth_status" in names


class TestNuggetsToolkitTls:
    def test_passes_ca_cert_to_client(self):
        toolkit = NuggetsToolkit(
            api_url="https://api.test",
            partner_id="pid",
            partner_secret="psec",
            ca_cert="/path/ca.pem",
        )
        assert toolkit._client._verify == "/path/ca.pem"

    def test_passes_verify_ssl_false_to_client(self):
        toolkit = NuggetsToolkit(
            api_url="https://api.test",
            partner_id="pid",
            partner_secret="psec",
            verify_ssl=False,
        )
        assert toolkit._client._verify is False
