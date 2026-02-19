"""Nuggets API client with automatic authentication and token caching."""
from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

import httpx


class NuggetsApiClientError(Exception):
    """Error from the Nuggets API."""

    def __init__(self, message: str, code: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class NuggetsApiClient:
    """HTTP client for the Nuggets API with automatic auth token management."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self._api_url: str = config["api_url"]
        self._partner_id: str = config["partner_id"]
        self._partner_secret: str = config["partner_secret"]
        self._token: Optional[Dict[str, Any]] = None
        self._sync_client: Optional[httpx.Client] = None
        self._async_client: Optional[httpx.AsyncClient] = None

    def _get_sync_client(self) -> httpx.Client:
        if self._sync_client is None:
            self._sync_client = httpx.Client()
        return self._sync_client

    def close(self) -> None:
        """Close the sync HTTP client and release resources."""
        if self._sync_client is not None:
            self._sync_client.close()
            self._sync_client = None

    async def aclose(self) -> None:
        """Close the async HTTP client and release resources."""
        if self._async_client is not None:
            await self._async_client.aclose()
            self._async_client = None

    def __enter__(self) -> "NuggetsApiClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    async def __aenter__(self) -> "NuggetsApiClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.aclose()

    def _authenticate_sync(self) -> str:
        if self._token and self._token["expires_at"] > time.time():
            return self._token["access_token"]
        client = self._get_sync_client()
        response = client.post(
            f"{self._api_url}/partner/auth",
            json={"partnerId": self._partner_id, "partnerSecret": self._partner_secret},
        )
        if response.status_code >= 400:
            raise NuggetsApiClientError(
                "Authentication failed", "AUTH_FAILED", response.status_code
            )
        data = response.json()
        self._token = {
            "access_token": data["token"],
            "expires_at": time.time() + data["expiresIn"],
        }
        return self._token["access_token"]

    def _request_sync(self, method: str, path: str, body: Any = None) -> Any:
        token = self._authenticate_sync()
        client = self._get_sync_client()
        kwargs: Dict[str, Any] = {
            "method": method,
            "url": f"{self._api_url}{path}",
            "headers": {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
        }
        if body is not None:
            kwargs["content"] = json.dumps(body)
        response = client.request(**kwargs)
        try:
            data = response.json()
        except Exception:
            if response.status_code >= 400:
                raise NuggetsApiClientError(
                    f"Request failed with status {response.status_code}",
                    "UNKNOWN",
                    response.status_code,
                )
            raise NuggetsApiClientError(
                "Invalid JSON response", "PARSE_ERROR", response.status_code
            )
        if response.status_code >= 400:
            raise NuggetsApiClientError(
                data.get("message", "Request failed"),
                data.get("code", "UNKNOWN"),
                response.status_code,
            )
        return data

    def get(self, path: str) -> Any:
        return self._request_sync("GET", path)

    def post(self, path: str, body: Any = None) -> Any:
        return self._request_sync("POST", path, body)

    # --- Async methods ---
    async def _get_async_client(self) -> httpx.AsyncClient:
        if self._async_client is None:
            self._async_client = httpx.AsyncClient()
        return self._async_client

    async def _authenticate_async(self) -> str:
        if self._token and self._token["expires_at"] > time.time():
            return self._token["access_token"]
        client = await self._get_async_client()
        response = await client.post(
            f"{self._api_url}/partner/auth",
            json={"partnerId": self._partner_id, "partnerSecret": self._partner_secret},
        )
        if response.status_code >= 400:
            raise NuggetsApiClientError(
                "Authentication failed", "AUTH_FAILED", response.status_code
            )
        data = response.json()
        self._token = {
            "access_token": data["token"],
            "expires_at": time.time() + data["expiresIn"],
        }
        return self._token["access_token"]

    async def _request_async(self, method: str, path: str, body: Any = None) -> Any:
        token = await self._authenticate_async()
        client = await self._get_async_client()
        kwargs: Dict[str, Any] = {
            "method": method,
            "url": f"{self._api_url}{path}",
            "headers": {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
        }
        if body is not None:
            kwargs["content"] = json.dumps(body)
        response = await client.request(**kwargs)
        try:
            data = response.json()
        except Exception:
            if response.status_code >= 400:
                raise NuggetsApiClientError(
                    f"Request failed with status {response.status_code}",
                    "UNKNOWN",
                    response.status_code,
                )
            raise NuggetsApiClientError(
                "Invalid JSON response", "PARSE_ERROR", response.status_code
            )
        if response.status_code >= 400:
            raise NuggetsApiClientError(
                data.get("message", "Request failed"),
                data.get("code", "UNKNOWN"),
                response.status_code,
            )
        return data

    async def aget(self, path: str) -> Any:
        return await self._request_async("GET", path)

    async def apost(self, path: str, body: Any = None) -> Any:
        return await self._request_async("POST", path, body)
