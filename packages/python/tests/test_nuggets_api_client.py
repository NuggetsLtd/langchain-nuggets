import json

import pytest
import respx
from httpx import Response

from langchain_nuggets.client.nuggets_api_client import NuggetsApiClient, NuggetsApiClientError

TEST_CONFIG = {
    "api_url": "https://api.nuggets.test",
    "partner_id": "partner-123",
    "partner_secret": "secret-456",
}

AUTH_RESPONSE = {"token": "auth-token", "expiresIn": 3600}


class TestNuggetsApiClient:
    def test_create_instance(self):
        client = NuggetsApiClient(TEST_CONFIG)
        assert client is not None

    @respx.mock
    def test_authenticated_get(self):
        respx.post("https://api.nuggets.test/partner/auth").mock(
            return_value=Response(200, json=AUTH_RESPONSE)
        )
        respx.get("https://api.nuggets.test/test").mock(
            return_value=Response(200, json={"data": "test"})
        )
        client = NuggetsApiClient(TEST_CONFIG)
        result = client.get("/test")
        assert result == {"data": "test"}

    @respx.mock
    def test_authenticated_post(self):
        respx.post("https://api.nuggets.test/partner/auth").mock(
            return_value=Response(200, json=AUTH_RESPONSE)
        )
        respx.post("https://api.nuggets.test/test").mock(
            return_value=Response(200, json={"id": "123"})
        )
        client = NuggetsApiClient(TEST_CONFIG)
        result = client.post("/test", {"body": "data"})
        assert result == {"id": "123"}

    @respx.mock
    def test_token_caching(self):
        auth_route = respx.post("https://api.nuggets.test/partner/auth").mock(
            return_value=Response(200, json=AUTH_RESPONSE)
        )
        respx.get("https://api.nuggets.test/first").mock(
            return_value=Response(200, json={"data": "first"})
        )
        respx.get("https://api.nuggets.test/second").mock(
            return_value=Response(200, json={"data": "second"})
        )
        client = NuggetsApiClient(TEST_CONFIG)
        client.get("/first")
        client.get("/second")
        assert auth_route.call_count == 1

    @respx.mock
    def test_auth_failure(self):
        respx.post("https://api.nuggets.test/partner/auth").mock(
            return_value=Response(401, json={"message": "Unauthorized"})
        )
        client = NuggetsApiClient(TEST_CONFIG)
        with pytest.raises(NuggetsApiClientError) as exc_info:
            client.get("/test")
        assert exc_info.value.code == "AUTH_FAILED"
        assert exc_info.value.status_code == 401

    @respx.mock
    def test_api_error(self):
        respx.post("https://api.nuggets.test/partner/auth").mock(
            return_value=Response(200, json=AUTH_RESPONSE)
        )
        respx.get("https://api.nuggets.test/missing").mock(
            return_value=Response(404, json={"code": "NOT_FOUND", "message": "Not found"})
        )
        client = NuggetsApiClient(TEST_CONFIG)
        with pytest.raises(NuggetsApiClientError) as exc_info:
            client.get("/missing")
        assert exc_info.value.code == "NOT_FOUND"
        assert str(exc_info.value) == "Not found"
