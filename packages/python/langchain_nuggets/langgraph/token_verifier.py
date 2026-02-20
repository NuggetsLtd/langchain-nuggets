"""OIDC token verification for the Nuggets auth provider."""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Union

import httpx
import jwt
from jwt import PyJWK


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
    ) -> None:
        self._issuer_url = issuer_url.rstrip("/")
        self._audience = audience
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
        """Verify an OIDC token and return its claims.

        Tries JWKS-based JWT verification first. If the token is not a valid
        JWT (e.g., opaque access token), falls back to the userinfo endpoint.

        Returns:
            Dict with at least a ``sub`` key.

        Raises:
            NuggetsAuthError: If verification fails.
        """
        try:
            return await self._verify_jwt(token)
        except (jwt.exceptions.DecodeError, jwt.exceptions.InvalidTokenError):
            # Token is not a JWT or has invalid structure — try userinfo
            pass

        return await self._fetch_userinfo(token)

    async def _verify_jwt(self, token: str) -> Dict[str, Any]:
        """Verify a JWT using the OIDC provider's JWKS."""
        # Get the kid from the JWT header
        try:
            unverified_header = jwt.get_unverified_header(token)
        except jwt.exceptions.DecodeError:
            raise

        kid = unverified_header.get("kid")
        alg = unverified_header.get("alg", "RS256")

        # Fetch and find the matching key
        signing_key = await self._get_signing_key(kid)

        try:
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=[alg],
                audience=self._audience if self._audience else None,
                issuer=self._issuer_url,
                options={"verify_aud": bool(self._audience)},
            )
        except jwt.ExpiredSignatureError:
            raise NuggetsAuthError("Token has expired", 401)
        except jwt.InvalidIssuerError:
            raise NuggetsAuthError("Invalid token issuer", 401)
        except jwt.InvalidAudienceError:
            raise NuggetsAuthError("Invalid token audience", 401)
        except jwt.InvalidTokenError as exc:
            raise NuggetsAuthError(f"Invalid token: {exc}", 401)

        if "sub" not in claims:
            raise NuggetsAuthError("Token missing required 'sub' claim", 401)

        return claims

    async def _get_signing_key(self, kid: Optional[str]) -> PyJWK:
        """Find the signing key matching the given kid from cached JWKS."""
        keys = await self._fetch_jwks()

        for key_data in keys:
            jwk = PyJWK(key_data)
            if kid is None or key_data.get("kid") == kid:
                return jwk

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

    async def _fetch_userinfo(self, token: str) -> Dict[str, Any]:
        """Fetch user information from the OIDC userinfo endpoint."""
        discovery = await self._discover_endpoints()
        userinfo_endpoint = discovery.get("userinfo_endpoint")
        if not userinfo_endpoint:
            raise NuggetsAuthError("OIDC provider does not expose a userinfo endpoint", 401)

        client = self._get_http_client()
        response = await client.get(
            userinfo_endpoint,
            headers={"Authorization": f"Bearer {token}"},
        )

        if response.status_code == 401:
            raise NuggetsAuthError("Invalid or expired token", 401)
        if response.status_code >= 400:
            raise NuggetsAuthError(
                f"Userinfo request failed with status {response.status_code}",
                response.status_code,
            )

        data = response.json()
        if "sub" not in data:
            raise NuggetsAuthError("Userinfo response missing required 'sub' field", 401)

        return data

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
