"""OIDC token verification for the Nuggets auth provider."""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Union

import httpx
import jwt
from jwt import PyJWK

logger = logging.getLogger(__name__)

# The Nuggets issuer signs access tokens with RS256. Never derive the accepted
# algorithm from the (attacker-controlled) token header — pin it here so a token
# presenting a different `alg` can't steer verification (RS/HS confusion, etc.).
_ALLOWED_ALGORITHMS = ["RS256"]

# RFC 9068 access-token type. Enforced to block ID-token/access-token confusion.
_EXPECTED_TYP = "at+jwt"

# Clock-skew tolerance (seconds) on exp/iat — matches the issuer's clockTolerance.
_CLOCK_SKEW_LEEWAY = 15


class NuggetsAuthError(Exception):
    """Authentication error from Nuggets token verification."""

    def __init__(self, message: str, status_code: int = 401) -> None:
        super().__init__(message)
        self.status_code = status_code


class NuggetsTokenVerifier:
    """Verifies OIDC tokens issued by the Nuggets identity provider.

    Supports two verification modes:
    1. JWKS-based JWT verification (preferred — no per-request network call)
    2. UserInfo endpoint introspection (fallback for opaque tokens)

    OIDC discovery is used to find the JWKS and userinfo endpoints from the
    issuer URL's .well-known/openid-configuration.
    """

    def __init__(
        self,
        issuer_url: str,
        audience: Optional[str] = None,
        jwks_cache_ttl: int = 3600,
        ca_cert: Optional[str] = None,
        verify_ssl: bool = True,
        allow_any_audience: bool = False,
    ) -> None:
        self._issuer_url = issuer_url.rstrip("/")
        # Normalize a blank/whitespace audience to None (a blank string is "not
        # configured", not an audience).
        normalized_audience = audience.strip() if isinstance(audience, str) else audience
        self._audience = normalized_audience or None
        # RFC 9068: a resource server must reject JWT access tokens whose `aud`
        # doesn't identify it. Verification fails closed when no `audience` is
        # configured. `allow_any_audience` is a deliberate, documented-insecure
        # escape hatch that bypasses ONLY the `aud` match — signature, `iss`,
        # `exp`, `typ`, and the RS256 pin all still apply.
        self._allow_any_audience = allow_any_audience
        if self._audience is None and self._allow_any_audience:
            logger.warning(
                "NuggetsTokenVerifier: allow_any_audience=True — JWT audience (aud) "
                "is NOT enforced. This is insecure and intended only for migration; "
                "set an audience for production."
            )
        self._jwks_cache_ttl = jwks_cache_ttl

        # TLS configuration for self-hosted deployments
        if not verify_ssl:
            self._verify: Union[bool, str] = False
        elif ca_cert is not None:
            self._verify = ca_cert
        else:
            self._verify = True

        # Cached OIDC discovery data
        self._discovery: Optional[Dict[str, Any]] = None
        self._discovery_fetched_at: float = 0

        # Cached JWKS keys
        self._jwks_keys: Optional[List[Dict[str, Any]]] = None
        self._jwks_fetched_at: float = 0

        # Reusable HTTP client
        self._http_client: Optional[httpx.AsyncClient] = None

    def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(verify=self._verify)
        return self._http_client

    async def aclose(self) -> None:
        """Close the HTTP client and release resources."""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def verify_token(self, token: str) -> Dict[str, Any]:
        """Verify an OIDC **JWT** access token and return its claims.

        JWT-only: a non-JWT (opaque) token is rejected, never sent to an
        unaudienced userinfo fallback that could bypass the audience check.
        Authenticated introspection for opaque tokens is a documented follow-up,
        not implemented here.

        Returns:
            Dict with at least a ``sub`` key.

        Raises:
            NuggetsAuthError: If verification fails.
        """
        return await self._verify_jwt(token)

    async def _verify_jwt(self, token: str) -> Dict[str, Any]:
        """Verify a JWT using the OIDC provider's JWKS."""
        # Fail closed if we can't enforce audience (RFC 9068), unless opted out.
        if self._audience is None and not self._allow_any_audience:
            raise NuggetsAuthError(
                "Refusing to verify a JWT without a configured audience. Pass "
                "audience=<your resource URI> (RFC 9068), or set "
                "allow_any_audience=True to explicitly disable this check (insecure).",
                401,
            )

        try:
            unverified_header = jwt.get_unverified_header(token)
        except jwt.exceptions.DecodeError:
            raise NuggetsAuthError(
                "Token is not a verifiable JWT; opaque tokens are not accepted (JWT-only).",
                401,
            )

        kid = unverified_header.get("kid")

        # Fetch and find the matching key
        signing_key = await self._get_signing_key(kid)

        try:
            claims: Dict[str, Any] = jwt.decode(
                token,
                signing_key.key,
                # Pinned allowlist — never the header's `alg`.
                algorithms=_ALLOWED_ALGORITHMS,
                audience=self._audience if self._audience else None,
                issuer=self._issuer_url,
                leeway=_CLOCK_SKEW_LEEWAY,
                options={"verify_aud": self._audience is not None},
            )
        except jwt.ExpiredSignatureError:
            raise NuggetsAuthError("Token has expired", 401)
        except jwt.InvalidIssuerError:
            raise NuggetsAuthError("Invalid token issuer", 401)
        except jwt.InvalidAudienceError:
            raise NuggetsAuthError("Invalid token audience", 401)
        except jwt.InvalidTokenError as exc:
            raise NuggetsAuthError(f"Invalid token: {exc}", 401)

        # Enforce the RFC 9068 access-token type. The protected header is signed,
        # so a successful decode means this typ is integrity-protected.
        if unverified_header.get("typ") != _EXPECTED_TYP:
            raise NuggetsAuthError(
                f"Unexpected token typ {unverified_header.get('typ')!r}; "
                f"expected {_EXPECTED_TYP!r} (RFC 9068 access token).",
                401,
            )

        if "sub" not in claims:
            raise NuggetsAuthError("Token missing required 'sub' claim", 401)

        return claims

    async def _get_signing_key(self, kid: Optional[str]) -> PyJWK:
        """Find the signing key matching the given kid from cached JWKS."""
        keys = await self._fetch_jwks()

        for key_data in keys:
            # Only consider RSA signing keys advertised for RS256 (or unspecified).
            # Skip encryption keys, EC/oct keys, and keys pinned to another alg —
            # this keeps key selection independent of the token header.
            if key_data.get("kty") != "RSA":
                continue
            if key_data.get("use") not in (None, "sig"):
                continue
            if key_data.get("alg") not in (None, "RS256"):
                continue
            if kid is None or key_data.get("kid") == kid:
                return PyJWK(key_data)

        raise NuggetsAuthError(f"No signing key found for kid={kid}", 401)

    async def _fetch_jwks(self) -> List[Dict[str, Any]]:
        """Fetch and cache the JWKS from the OIDC provider."""
        now = time.time()
        if self._jwks_keys and (now - self._jwks_fetched_at) < self._jwks_cache_ttl:
            return self._jwks_keys

        discovery = await self._discover_endpoints()
        jwks_uri = discovery.get("jwks_uri")
        if not jwks_uri:
            raise NuggetsAuthError("OIDC provider does not expose a jwks_uri", 500)

        client = self._get_http_client()
        response = await client.get(jwks_uri)

        if response.status_code >= 400:
            raise NuggetsAuthError(f"JWKS fetch failed: {response.status_code}", 500)

        data = response.json()
        self._jwks_keys = data.get("keys", [])
        self._jwks_fetched_at = now
        return self._jwks_keys

    async def _discover_endpoints(self) -> Dict[str, Any]:
        """Fetch and cache the OIDC discovery document."""
        now = time.time()
        if self._discovery and (now - self._discovery_fetched_at) < self._jwks_cache_ttl:
            return self._discovery

        url = f"{self._issuer_url}/.well-known/openid-configuration"
        client = self._get_http_client()
        response = await client.get(url)

        if response.status_code >= 400:
            raise NuggetsAuthError(
                f"OIDC discovery failed: {response.status_code}", 500
            )

        self._discovery = response.json()
        self._discovery_fetched_at = now
        return self._discovery
