"""OIDC client_credentials + private_key_jwt token exchange.

The authority middleware authenticates HTTP requests to /api/authority/evaluate
by exchanging the agent's private key for a short-lived access token at the
Nuggets OIDC provider, then sending that token as a Bearer header.

See NuggetsLtd/partner#119 — the backend verifies the token's issuer, audience,
and client_id claims against its registered JWKS.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, Optional, Union

import httpx
import jwt

_DEFAULT_SCOPE = "authority.evaluate"
_DEFAULT_ASSERTION_TTL_SECONDS = 300
_REFRESH_BEFORE_EXPIRY_SECONDS = 30


class OidcClientCredentialsClient:
    """OAuth 2.0 client_credentials flow with private_key_jwt client auth.

    Signs a client_assertion JWT with the agent's private key, exchanges it
    for an access token at the OIDC token endpoint, and caches the token
    until shortly before expiry.

    On each post(): refreshes the token if needed, then sends the request
    with Authorization: Bearer <token>.
    """

    def __init__(
        self,
        *,
        issuer_url: str,
        client_id: str,
        private_key_pem: str,
        scope: str = _DEFAULT_SCOPE,
        verify_ssl: bool = True,
        ca_cert: Optional[str] = None,
    ) -> None:
        self._issuer_url = issuer_url.rstrip("/")
        self._token_endpoint = f"{self._issuer_url}/token"
        self._client_id = client_id
        self._private_key_pem = private_key_pem
        self._scope = scope
        self._token: Optional[Dict[str, Any]] = None
        self._sync_client: Optional[httpx.Client] = None
        self._async_client: Optional[httpx.AsyncClient] = None

        if not verify_ssl:
            self._verify: Union[bool, str] = False
        elif ca_cert is not None:
            self._verify = ca_cert
        else:
            self._verify = True

    def _build_client_assertion(self) -> str:
        now = int(time.time())
        payload = {
            "iss": self._client_id,
            "sub": self._client_id,
            "aud": self._token_endpoint,
            "iat": now,
            "exp": now + _DEFAULT_ASSERTION_TTL_SECONDS,
            "jti": str(uuid.uuid4()),
        }
        return jwt.encode(payload, self._private_key_pem, algorithm="RS256")

    def _token_is_fresh(self) -> bool:
        if self._token is None:
            return False
        return self._token["expires_at"] > time.time() + _REFRESH_BEFORE_EXPIRY_SECONDS

    def _store_token(self, response_body: Dict[str, Any]) -> str:
        self._token = {
            "access_token": response_body["access_token"],
            "expires_at": time.time() + int(response_body.get("expires_in", 3600)),
        }
        return self._token["access_token"]

    def _token_request_form(self) -> Dict[str, str]:
        return {
            "grant_type": "client_credentials",
            "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
            "client_assertion": self._build_client_assertion(),
            "scope": self._scope,
        }

    def _get_sync_client(self) -> httpx.Client:
        if self._sync_client is None:
            self._sync_client = httpx.Client(verify=self._verify)
        return self._sync_client

    async def _get_async_client(self) -> httpx.AsyncClient:
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(verify=self._verify)
        return self._async_client

    def get_access_token(self) -> str:
        if self._token_is_fresh():
            return self._token["access_token"]  # type: ignore[index]
        client = self._get_sync_client()
        response = client.post(self._token_endpoint, data=self._token_request_form())
        if response.status_code >= 400:
            raise OidcTokenError(
                f"token exchange failed: {response.status_code} {response.text}",
                response.status_code,
            )
        return self._store_token(response.json())

    async def aget_access_token(self) -> str:
        if self._token_is_fresh():
            return self._token["access_token"]  # type: ignore[index]
        client = await self._get_async_client()
        response = await client.post(self._token_endpoint, data=self._token_request_form())
        if response.status_code >= 400:
            raise OidcTokenError(
                f"token exchange failed: {response.status_code} {response.text}",
                response.status_code,
            )
        return self._store_token(response.json())

    def post(
        self,
        url: str,
        body: Any,
        *,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        token = self.get_access_token()
        merged = _merge_headers(token, headers)
        client = self._get_sync_client()
        response = client.post(url, content=json.dumps(body), headers=merged)
        return _decode_response(response)

    async def apost(
        self,
        url: str,
        body: Any,
        *,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        token = await self.aget_access_token()
        merged = _merge_headers(token, headers)
        client = await self._get_async_client()
        response = await client.post(url, content=json.dumps(body), headers=merged)
        return _decode_response(response)

    def close(self) -> None:
        if self._sync_client is not None:
            self._sync_client.close()
            self._sync_client = None

    async def aclose(self) -> None:
        if self._async_client is not None:
            await self._async_client.aclose()
            self._async_client = None


class OidcTokenError(Exception):
    """Raised when the OIDC token endpoint rejects the assertion."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


_RESERVED_HEADERS = frozenset({"authorization", "content-type"})


def _merge_headers(token: str, extra: Optional[Dict[str, str]]) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    if extra:
        for key, value in extra.items():
            if key.lower() in _RESERVED_HEADERS:
                continue
            headers[key] = value
    headers["Content-Type"] = "application/json"
    headers["Authorization"] = f"Bearer {token}"
    return headers


def _decode_response(response: httpx.Response) -> Any:
    try:
        data = response.json()
    except Exception:
        if response.status_code >= 400:
            raise OidcTokenError(
                f"request failed with status {response.status_code}",
                response.status_code,
            )
        raise OidcTokenError("invalid JSON response", response.status_code)
    if response.status_code >= 400:
        raise OidcTokenError(
            data.get("message", "request failed"),
            response.status_code,
        )
    return data
