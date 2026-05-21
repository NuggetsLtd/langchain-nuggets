"""Tests for OidcClientCredentialsClient."""
import time

import jwt
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import Response

from langchain_nuggets.middleware.oidc_client import (
    OidcClientCredentialsClient,
    OidcTokenError,
)


@pytest.fixture(scope="module")
def rsa_keypair():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = (
        priv.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
    return {"private_pem": private_pem, "public_pem": public_pem}


@pytest.fixture
def client(rsa_keypair):
    return OidcClientCredentialsClient(
        issuer_url="https://auth.test",
        client_id="did:web:auth.test:abc",
        private_key_pem=rsa_keypair["private_pem"],
    )


class TestClientAssertion:
    def test_builds_jws_with_correct_claims(self, client, rsa_keypair):
        assertion = client._build_client_assertion()
        decoded = jwt.decode(
            assertion,
            rsa_keypair["public_pem"],
            algorithms=["RS256"],
            audience="https://auth.test/token",
        )
        assert decoded["iss"] == "did:web:auth.test:abc"
        assert decoded["sub"] == "did:web:auth.test:abc"
        assert decoded["aud"] == "https://auth.test/token"
        assert len(decoded["jti"]) == 36
        assert decoded["exp"] > decoded["iat"]

    def test_fresh_jti_per_call(self, client):
        a = client._build_client_assertion()
        b = client._build_client_assertion()
        assert jwt.decode(a, options={"verify_signature": False})["jti"] != jwt.decode(
            b, options={"verify_signature": False}
        )["jti"]


class TestTokenExchange:
    @respx.mock
    def test_exchanges_assertion_for_access_token(self, client):
        route = respx.post("https://auth.test/token").mock(
            return_value=Response(200, json={"access_token": "tok-1", "expires_in": 3600})
        )
        token = client.get_access_token()
        assert token == "tok-1"
        form = route.calls.last.request.content.decode()
        assert "grant_type=client_credentials" in form
        assert "client_assertion=" in form
        assert "scope=authority.evaluate" in form

    @respx.mock
    def test_caches_token_until_near_expiry(self, client):
        route = respx.post("https://auth.test/token").mock(
            return_value=Response(200, json={"access_token": "tok-1", "expires_in": 3600})
        )
        a = client.get_access_token()
        b = client.get_access_token()
        assert a == b
        assert route.call_count == 1

    @respx.mock
    def test_refreshes_when_token_about_to_expire(self, client):
        route = respx.post("https://auth.test/token").mock(
            side_effect=[
                Response(200, json={"access_token": "tok-1", "expires_in": 3600}),
                Response(200, json={"access_token": "tok-2", "expires_in": 3600}),
            ]
        )
        client.get_access_token()
        client._token["expires_at"] = time.time() + 10  # force near-expiry
        second = client.get_access_token()
        assert second == "tok-2"
        assert route.call_count == 2

    @respx.mock
    def test_token_endpoint_failure_raises(self, client):
        respx.post("https://auth.test/token").mock(
            return_value=Response(401, json={"error": "invalid_client"})
        )
        with pytest.raises(OidcTokenError) as exc_info:
            client.get_access_token()
        assert exc_info.value.status_code == 401
        # error message includes OAuth error code but not raw body
        assert "invalid_client" in str(exc_info.value)

    @respx.mock
    def test_token_endpoint_error_message_excludes_raw_body(self, client):
        respx.post("https://auth.test/token").mock(
            return_value=Response(500, text="<html>internal server secret leak</html>")
        )
        with pytest.raises(OidcTokenError) as exc_info:
            client.get_access_token()
        assert "internal server secret leak" not in str(exc_info.value)
        assert exc_info.value.status_code == 500

    @respx.mock
    def test_malformed_response_raises_oidc_token_error(self, client):
        respx.post("https://auth.test/token").mock(
            return_value=Response(200, text="not-json")
        )
        with pytest.raises(OidcTokenError):
            client.get_access_token()

    @respx.mock
    def test_missing_access_token_raises_oidc_token_error(self, client):
        respx.post("https://auth.test/token").mock(
            return_value=Response(200, json={"expires_in": 3600})
        )
        with pytest.raises(OidcTokenError) as exc_info:
            client.get_access_token()
        assert "access_token" in str(exc_info.value)


class TestAuthenticatedPost:
    @respx.mock
    def test_post_includes_bearer_header(self, client):
        respx.post("https://auth.test/token").mock(
            return_value=Response(200, json={"access_token": "tok-1", "expires_in": 3600})
        )
        api_route = respx.post("https://api.test/api/authority/evaluate").mock(
            return_value=Response(200, json={"decision": "ALLOW"})
        )
        client.post("https://api.test/api/authority/evaluate", {"x": 1})
        sent = api_route.calls.last.request.headers
        assert sent["Authorization"] == "Bearer tok-1"
        assert sent["Content-Type"] == "application/json"

    @respx.mock
    def test_post_caller_cannot_override_authorization(self, client):
        respx.post("https://auth.test/token").mock(
            return_value=Response(200, json={"access_token": "tok-1", "expires_in": 3600})
        )
        api_route = respx.post("https://api.test/api/authority/evaluate").mock(
            return_value=Response(200, json={"decision": "ALLOW"})
        )
        client.post(
            "https://api.test/api/authority/evaluate",
            {"x": 1},
            headers={"Authorization": "Bearer attacker", "Idempotency-Key": "k1"},
        )
        sent = api_route.calls.last.request.headers
        assert sent["Authorization"] == "Bearer tok-1"
        assert sent["Idempotency-Key"] == "k1"

    @respx.mock
    async def test_async_post_includes_bearer(self, client):
        respx.post("https://auth.test/token").mock(
            return_value=Response(200, json={"access_token": "tok-1", "expires_in": 3600})
        )
        api_route = respx.post("https://api.test/api/authority/evaluate").mock(
            return_value=Response(200, json={"decision": "ALLOW"})
        )
        await client.apost("https://api.test/api/authority/evaluate", {"x": 1})
        sent = api_route.calls.last.request.headers
        assert sent["Authorization"] == "Bearer tok-1"
