"""Nuggets authentication provider for LangGraph Platform."""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

try:
    from langgraph_sdk import Auth
except ImportError:
    raise ImportError(
        "langgraph-sdk is required for LangGraph auth integration. "
        "Install it with: pip install langchain-nuggets[langgraph]"
    )

from langchain_nuggets.langgraph.token_verifier import NuggetsAuthError, NuggetsTokenVerifier


class NuggetsAuth:
    """Pre-configured LangGraph Auth provider backed by Nuggets OIDC.

    Verifies bearer tokens from the Nuggets OIDC provider and returns
    user identity information to LangGraph.

    Usage::

        from langchain_nuggets.langgraph import NuggetsAuth

        nuggets_auth = NuggetsAuth(
            issuer_url="https://auth.nuggets.life",
        )
        auth = nuggets_auth.auth  # pass to langgraph.json

    Or with environment variables::

        # Set NUGGETS_OIDC_ISSUER_URL
        nuggets_auth = NuggetsAuth()
        auth = nuggets_auth.auth
    """

    def __init__(
        self,
        issuer_url: Optional[str] = None,
        audience: Optional[str] = None,
        ca_cert: Optional[str] = None,
        verify_ssl: bool = True,
        allow_any_audience: bool = False,
    ) -> None:
        resolved_issuer = issuer_url or os.environ.get("NUGGETS_OIDC_ISSUER_URL", "")
        if not resolved_issuer:
            raise ValueError(
                "NuggetsAuth requires issuer_url. "
                "Pass it explicitly or set NUGGETS_OIDC_ISSUER_URL."
            )

        self._verifier = NuggetsTokenVerifier(
            issuer_url=resolved_issuer,
            audience=audience,
            ca_cert=ca_cert,
            verify_ssl=verify_ssl,
            allow_any_audience=allow_any_audience,
        )

        # Create and configure the LangGraph Auth object
        self._auth = Auth()
        self._auth.authenticate(self._authenticate)

    @property
    def auth(self) -> Auth:
        """The configured LangGraph Auth object.

        Pass this to your ``langgraph.json`` auth config::

            # auth.py
            nuggets = NuggetsAuth()
            auth = nuggets.auth
        """
        return self._auth

    async def _authenticate(self, authorization: Optional[str] = None) -> Dict[str, Any]:
        """LangGraph authenticate handler.

        Extracts the bearer token, verifies it via OIDC, and returns a
        MinimalUserDict.
        """
        if not authorization or not authorization.startswith("Bearer "):
            raise Auth.exceptions.HTTPException(
                status_code=401,
                detail="Missing or invalid Authorization header",
            )

        token = authorization[7:]  # Strip "Bearer "

        try:
            claims = await self._verifier.verify_token(token)
        except NuggetsAuthError as exc:
            raise Auth.exceptions.HTTPException(
                status_code=exc.status_code,
                detail=str(exc),
            )

        user_dict: Dict[str, Any] = {
            "identity": claims["sub"],
            "is_authenticated": True,
            "permissions": (
                claims.get("scope", "").split()
                if isinstance(claims.get("scope"), str)
                else claims.get("scope", [])
            ),
        }

        for field in ("email", "name", "given_name", "family_name"):
            if field in claims:
                user_dict[field] = claims[field]

        # Mirror permissions under "scopes" for the authorization helpers.
        user_dict["scopes"] = user_dict["permissions"]

        return user_dict
