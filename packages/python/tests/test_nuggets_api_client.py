
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


class TestNuggetsApiClientTls:
    def test_default_verify_is_true(self):
        client = NuggetsApiClient(TEST_CONFIG)
        assert client._verify is True

    def test_ca_cert_sets_verify_path(self):
        config = {**TEST_CONFIG, "ca_cert": "/path/to/ca.pem"}
        client = NuggetsApiClient(config)
        assert client._verify == "/path/to/ca.pem"

    def test_verify_ssl_false_disables_verification(self):
        config = {**TEST_CONFIG, "verify_ssl": False}
        client = NuggetsApiClient(config)
        assert client._verify is False

    def test_verify_ssl_false_takes_precedence_over_ca_cert(self):
        config = {**TEST_CONFIG, "verify_ssl": False, "ca_cert": "/path/ca.pem"}
        client = NuggetsApiClient(config)
        assert client._verify is False

    def test_sync_client_uses_verify(self):
        config = {**TEST_CONFIG, "ca_cert": "/path/to/ca.pem"}
        client = NuggetsApiClient(config)
        with pytest.raises(Exception):
            # The path doesn't exist, so httpx will raise when creating the client
            # This verifies the verify param is actually passed through
            client._get_sync_client()


class TestNuggetsApiClientHeaders:
    @respx.mock
    def test_custom_header_included(self):
        respx.post("https://api.nuggets.test/partner/auth").mock(
            return_value=Response(200, json=AUTH_RESPONSE)
        )
        route = respx.post("https://api.nuggets.test/x").mock(
            return_value=Response(200, json={"ok": True})
        )
        client = NuggetsApiClient(TEST_CONFIG)
        client.post("/x", {"k": "v"}, headers={"Idempotency-Key": "abc-123"})
        sent = route.calls.last.request.headers
        assert sent["Idempotency-Key"] == "abc-123"
        assert sent["Authorization"] == "Bearer auth-token"
        assert sent["Content-Type"] == "application/json"

    @respx.mock
    def test_caller_cannot_override_authorization(self):
        respx.post("https://api.nuggets.test/partner/auth").mock(
            return_value=Response(200, json=AUTH_RESPONSE)
        )
        route = respx.post("https://api.nuggets.test/x").mock(
            return_value=Response(200, json={"ok": True})
        )
        client = NuggetsApiClient(TEST_CONFIG)
        client.post(
            "/x",
            {"k": "v"},
            headers={"Authorization": "Bearer attacker", "authorization": "lowercase"},
        )
        sent = route.calls.last.request.headers
        assert sent["Authorization"] == "Bearer auth-token"

    @respx.mock
    def test_caller_cannot_override_content_type(self):
        respx.post("https://api.nuggets.test/partner/auth").mock(
            return_value=Response(200, json=AUTH_RESPONSE)
        )
        route = respx.post("https://api.nuggets.test/x").mock(
            return_value=Response(200, json={"ok": True})
        )
        client = NuggetsApiClient(TEST_CONFIG)
        client.post("/x", {"k": "v"}, headers={"Content-Type": "text/plain"})
        sent = route.calls.last.request.headers
        assert sent["Content-Type"] == "application/json"

    @respx.mock
    async def test_async_custom_header_included(self):
        respx.post("https://api.nuggets.test/partner/auth").mock(
            return_value=Response(200, json=AUTH_RESPONSE)
        )
        route = respx.post("https://api.nuggets.test/x").mock(
            return_value=Response(200, json={"ok": True})
        )
        client = NuggetsApiClient(TEST_CONFIG)
        await client.apost("/x", {"k": "v"}, headers={"Idempotency-Key": "abc-123"})
        sent = route.calls.last.request.headers
        assert sent["Idempotency-Key"] == "abc-123"
        assert sent["Authorization"] == "Bearer auth-token"

    @respx.mock
    async def test_async_caller_cannot_override_authorization(self):
        respx.post("https://api.nuggets.test/partner/auth").mock(
            return_value=Response(200, json=AUTH_RESPONSE)
        )
        route = respx.post("https://api.nuggets.test/x").mock(
            return_value=Response(200, json={"ok": True})
        )
        client = NuggetsApiClient(TEST_CONFIG)
        await client.apost(
            "/x", {"k": "v"}, headers={"Authorization": "Bearer attacker"}
        )
        sent = route.calls.last.request.headers
        assert sent["Authorization"] == "Bearer auth-token"
