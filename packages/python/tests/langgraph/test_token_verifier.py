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


def _make_jwt(
    claims: dict,
    *,
    expired: bool = False,
    exp_offset: int | None = None,
    issuer: str = ISSUER,
    aud: str = "test-audience",
    typ: str | None = "at+jwt",
) -> str:
    if exp_offset is None:
        exp_offset = -3600 if expired else 3600
    payload = {
        "sub": "user-123",
        "iss": issuer,
        "aud": aud,
        "iat": int(time.time()),
        "exp": int(time.time()) + exp_offset,
        **claims,
    }
    headers = {"kid": "test-key-1"}
    if typ is not None:
        headers["typ"] = typ
    return jwt.encode(payload, _private_key, algorithm="RS256", headers=headers)


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
async def test_opaque_token_rejected():
    # JWT-only: a non-JWT (opaque) token is rejected, never sent to a userinfo
    # fallback that would bypass the audience check.
    _mock_discovery_and_jwks()
    verifier = NuggetsTokenVerifier(ISSUER, audience="test-audience")

    with pytest.raises(NuggetsAuthError):
        await verifier.verify_token("opaque-access-token-xyz")


@respx.mock
@pytest.mark.asyncio
async def test_missing_sub_claim():
    _mock_discovery_and_jwks()
    verifier = NuggetsTokenVerifier(ISSUER, allow_any_audience=True)

    # A verifiable JWT (correct typ/iss/sig) but without 'sub'.
    token = jwt.encode(
        {
            "iss": ISSUER,
            "aud": "test-audience",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
            "email": "no-sub@example.com",
        },
        _private_key,
        algorithm="RS256",
        headers={"kid": "test-key-1", "typ": "at+jwt"},
    )

    with pytest.raises(NuggetsAuthError, match="sub"):
        await verifier.verify_token(token)


@respx.mock
@pytest.mark.asyncio
async def test_rejects_non_rs256_algorithm():
    # #5: the verification algorithm must NOT be taken from the token header.
    # A token signed with a different (still asymmetric) alg must be rejected.
    _mock_discovery_and_jwks()
    verifier = NuggetsTokenVerifier(ISSUER, audience="test-audience")
    payload = {
        "sub": "user-123",
        "iss": ISSUER,
        "aud": "test-audience",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    token = jwt.encode(
        payload, _private_key, algorithm="RS512", headers={"kid": "test-key-1"}
    )

    with pytest.raises(NuggetsAuthError):
        await verifier.verify_token(token)


@respx.mock
@pytest.mark.asyncio
async def test_jwt_without_configured_audience_is_rejected():
    # Mandatory audience (#63 contract now live): no audience configured → fail
    # closed, rather than accept any correctly-signed issuer token.
    _mock_discovery_and_jwks()
    verifier = NuggetsTokenVerifier(ISSUER)
    token = _make_jwt({})

    with pytest.raises(NuggetsAuthError, match="audience"):
        await verifier.verify_token(token)


@respx.mock
@pytest.mark.asyncio
async def test_blank_audience_is_rejected():
    # Blank/whitespace normalizes to None → same fail-closed path.
    _mock_discovery_and_jwks()
    verifier = NuggetsTokenVerifier(ISSUER, audience="   ")
    token = _make_jwt({})

    with pytest.raises(NuggetsAuthError, match="audience"):
        await verifier.verify_token(token)


@respx.mock
@pytest.mark.asyncio
async def test_rejects_wrong_typ():
    # typ must be at+jwt (RFC 9068) — blocks ID-token/access-token confusion.
    _mock_discovery_and_jwks()
    verifier = NuggetsTokenVerifier(ISSUER, audience="test-audience")
    token = _make_jwt({}, typ="JWT")

    with pytest.raises(NuggetsAuthError, match="typ"):
        await verifier.verify_token(token)


@respx.mock
@pytest.mark.asyncio
async def test_rejects_missing_typ():
    _mock_discovery_and_jwks()
    verifier = NuggetsTokenVerifier(ISSUER, audience="test-audience")
    token = _make_jwt({}, typ=None)

    with pytest.raises(NuggetsAuthError, match="typ"):
        await verifier.verify_token(token)


@respx.mock
@pytest.mark.asyncio
async def test_clock_skew_within_leeway_accepted():
    # Backend runs clockTolerance 15s; a token expired 10s ago still verifies.
    _mock_discovery_and_jwks()
    verifier = NuggetsTokenVerifier(ISSUER, audience="test-audience")
    token = _make_jwt({}, exp_offset=-10)

    claims = await verifier.verify_token(token)

    assert claims["sub"] == "user-123"


@respx.mock
@pytest.mark.asyncio
async def test_clock_skew_beyond_leeway_rejected():
    _mock_discovery_and_jwks()
    verifier = NuggetsTokenVerifier(ISSUER, audience="test-audience")
    token = _make_jwt({}, exp_offset=-120)

    with pytest.raises(NuggetsAuthError, match="expired"):
        await verifier.verify_token(token)


class TestAllowAnyAudience:
    """The opt-out bypasses ONLY the aud match — signature, iss, exp, typ,
    and RS256 pinning still apply. It is 'allow any audience', not 'allow
    anything'."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_bypasses_aud_only(self):
        _mock_discovery_and_jwks()
        verifier = NuggetsTokenVerifier(ISSUER, allow_any_audience=True)
        token = _make_jwt({}, aud="some-other-audience")

        claims = await verifier.verify_token(token)

        assert claims["sub"] == "user-123"

    @respx.mock
    @pytest.mark.asyncio
    async def test_still_rejects_wrong_issuer(self):
        _mock_discovery_and_jwks()
        verifier = NuggetsTokenVerifier(ISSUER, allow_any_audience=True)
        token = _make_jwt({}, issuer="https://evil.com")

        with pytest.raises(NuggetsAuthError, match="issuer"):
            await verifier.verify_token(token)

    @respx.mock
    @pytest.mark.asyncio
    async def test_still_rejects_expired(self):
        _mock_discovery_and_jwks()
        verifier = NuggetsTokenVerifier(ISSUER, allow_any_audience=True)
        token = _make_jwt({}, expired=True)

        with pytest.raises(NuggetsAuthError, match="expired"):
            await verifier.verify_token(token)

    @respx.mock
    @pytest.mark.asyncio
    async def test_still_rejects_bad_typ(self):
        _mock_discovery_and_jwks()
        verifier = NuggetsTokenVerifier(ISSUER, allow_any_audience=True)
        token = _make_jwt({}, typ="JWT")

        with pytest.raises(NuggetsAuthError, match="typ"):
            await verifier.verify_token(token)


@respx.mock
@pytest.mark.asyncio
async def test_discovery_caches_across_calls():
    # Discovery is fetched once and reused (exercised via the JWT/JWKS path).
    discovery_route = respx.get(DISCOVERY_URL).mock(
        return_value=httpx.Response(200, json=DISCOVERY_RESPONSE)
    )
    respx.get(JWKS_URL).mock(return_value=httpx.Response(200, json=_jwks_response))

    verifier = NuggetsTokenVerifier(ISSUER, audience="test-audience")

    await verifier.verify_token(_make_jwt({}))
    await verifier.verify_token(_make_jwt({}))

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
