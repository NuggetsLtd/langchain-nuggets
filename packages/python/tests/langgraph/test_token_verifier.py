"""Tests for the Nuggets OIDC token verifier."""
from __future__ import annotations

import base64
import time

import httpx
import jwt
import pytest
import respx
from cryptography.hazmat.primitives.asymmetric import rsa

from langchain_nuggets.langgraph.token_verifier import NuggetsAuthError, NuggetsTokenVerifier

# --- Test RSA key pair ---

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_public_key = _private_key.public_key()
_public_numbers = _public_key.public_numbers()


def _int_to_base64url(n: int, length: int | None = None) -> str:
    byte_length = length or (n.bit_length() + 7) // 8
    return base64.urlsafe_b64encode(n.to_bytes(byte_length, "big")).rstrip(b"=").decode()


_jwks_response = {
    "keys": [
        {
            "kty": "RSA",
            "kid": "test-key-1",
            "use": "sig",
            "alg": "RS256",
            "n": _int_to_base64url(_public_numbers.n, 256),
            "e": _int_to_base64url(_public_numbers.e, 3),
        }
    ]
}

ISSUER = "https://oidc.nuggets.test"
DISCOVERY_URL = f"{ISSUER}/.well-known/openid-configuration"
JWKS_URL = f"{ISSUER}/jwks"
USERINFO_URL = f"{ISSUER}/me"

DISCOVERY_RESPONSE = {
    "issuer": ISSUER,
    "jwks_uri": JWKS_URL,
    "userinfo_endpoint": USERINFO_URL,
}


def _make_jwt(claims: dict, expired: bool = False, issuer: str = ISSUER) -> str:
    payload = {
        "sub": "user-123",
        "iss": issuer,
        "aud": "test-audience",
        "iat": int(time.time()),
        "exp": int(time.time()) + (-3600 if expired else 3600),
        **claims,
    }
    return jwt.encode(
        payload, _private_key, algorithm="RS256", headers={"kid": "test-key-1"}
    )


def _mock_discovery_and_jwks():
    """Set up respx routes for OIDC discovery and JWKS."""
    respx.get(DISCOVERY_URL).mock(return_value=httpx.Response(200, json=DISCOVERY_RESPONSE))
    respx.get(JWKS_URL).mock(return_value=httpx.Response(200, json=_jwks_response))


@respx.mock
@pytest.mark.asyncio
async def test_verify_valid_jwt():
    _mock_discovery_and_jwks()
    verifier = NuggetsTokenVerifier(ISSUER, audience="test-audience")
    token = _make_jwt({"email": "alice@example.com"})

    claims = await verifier.verify_token(token)

    assert claims["sub"] == "user-123"
    assert claims["email"] == "alice@example.com"


@respx.mock
@pytest.mark.asyncio
async def test_verify_expired_jwt():
    _mock_discovery_and_jwks()
    verifier = NuggetsTokenVerifier(ISSUER, audience="test-audience")
    token = _make_jwt({}, expired=True)

    with pytest.raises(NuggetsAuthError, match="expired"):
        await verifier.verify_token(token)


@respx.mock
@pytest.mark.asyncio
async def test_verify_wrong_issuer():
    _mock_discovery_and_jwks()
    verifier = NuggetsTokenVerifier(ISSUER, audience="test-audience")
    token = _make_jwt({}, issuer="https://evil.com")

    with pytest.raises(NuggetsAuthError, match="issuer"):
        await verifier.verify_token(token)


@respx.mock
@pytest.mark.asyncio
async def test_verify_wrong_audience():
    _mock_discovery_and_jwks()
    verifier = NuggetsTokenVerifier(ISSUER, audience="correct-audience")
    token = _make_jwt({})  # aud = "test-audience"

    with pytest.raises(NuggetsAuthError, match="audience"):
        await verifier.verify_token(token)


@respx.mock
@pytest.mark.asyncio
async def test_jwks_caching():
    discovery_route = respx.get(DISCOVERY_URL).mock(
        return_value=httpx.Response(200, json=DISCOVERY_RESPONSE)
    )
    respx.get(JWKS_URL).mock(return_value=httpx.Response(200, json=_jwks_response))

    verifier = NuggetsTokenVerifier(ISSUER, audience="test-audience")

    token1 = _make_jwt({"email": "a@b.com"})
    token2 = _make_jwt({"email": "c@d.com"})

    await verifier.verify_token(token1)
    await verifier.verify_token(token2)

    # Discovery should only be fetched once (cached)
    assert discovery_route.call_count == 1


@respx.mock
@pytest.mark.asyncio
async def test_opaque_token_falls_back_to_userinfo():
    respx.get(DISCOVERY_URL).mock(return_value=httpx.Response(200, json=DISCOVERY_RESPONSE))
    respx.get(USERINFO_URL).mock(
        return_value=httpx.Response(200, json={"sub": "user-456", "email": "bob@example.com"})
    )

    verifier = NuggetsTokenVerifier(ISSUER)
    claims = await verifier.verify_token("opaque-access-token-xyz")

    assert claims["sub"] == "user-456"
    assert claims["email"] == "bob@example.com"


@respx.mock
@pytest.mark.asyncio
async def test_userinfo_success():
    respx.get(DISCOVERY_URL).mock(return_value=httpx.Response(200, json=DISCOVERY_RESPONSE))
    respx.get(USERINFO_URL).mock(
        return_value=httpx.Response(200, json={"sub": "user-789", "name": "Charlie"})
    )

    verifier = NuggetsTokenVerifier(ISSUER)
    claims = await verifier._fetch_userinfo("some-token")

    assert claims["sub"] == "user-789"
    assert claims["name"] == "Charlie"


@respx.mock
@pytest.mark.asyncio
async def test_userinfo_401():
    respx.get(DISCOVERY_URL).mock(return_value=httpx.Response(200, json=DISCOVERY_RESPONSE))
    respx.get(USERINFO_URL).mock(return_value=httpx.Response(401))

    verifier = NuggetsTokenVerifier(ISSUER)

    with pytest.raises(NuggetsAuthError, match="Invalid or expired token"):
        await verifier._fetch_userinfo("bad-token")


@respx.mock
@pytest.mark.asyncio
async def test_missing_sub_claim():
    _mock_discovery_and_jwks()
    verifier = NuggetsTokenVerifier(ISSUER)

    # Create a JWT without 'sub'
    payload = {
        "iss": ISSUER,
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
        "email": "no-sub@example.com",
    }
    token = jwt.encode(payload, _private_key, algorithm="RS256", headers={"kid": "test-key-1"})

    with pytest.raises(NuggetsAuthError, match="sub"):
        await verifier.verify_token(token)


@respx.mock
@pytest.mark.asyncio
async def test_discovery_caches_endpoints():
    discovery_route = respx.get(DISCOVERY_URL).mock(
        return_value=httpx.Response(200, json=DISCOVERY_RESPONSE)
    )
    respx.get(USERINFO_URL).mock(return_value=httpx.Response(200, json={"sub": "u1"}))

    verifier = NuggetsTokenVerifier(ISSUER)

    await verifier._fetch_userinfo("token1")
    await verifier._fetch_userinfo("token2")

    # Discovery fetched once, cached for second call
    assert discovery_route.call_count == 1


class TestTokenVerifierTls:
    def test_default_verify_is_true(self):
        verifier = NuggetsTokenVerifier(issuer_url="https://oidc.test")
        assert verifier._verify is True

    def test_ca_cert_sets_verify_path(self):
        verifier = NuggetsTokenVerifier(
            issuer_url="https://oidc.test", ca_cert="/etc/ssl/ca.pem"
        )
        assert verifier._verify == "/etc/ssl/ca.pem"

    def test_verify_ssl_false_disables_verification(self):
        verifier = NuggetsTokenVerifier(
            issuer_url="https://oidc.test", verify_ssl=False
        )
        assert verifier._verify is False
