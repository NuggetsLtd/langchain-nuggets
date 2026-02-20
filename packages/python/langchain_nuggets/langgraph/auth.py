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

from langchain_nuggets.client.nuggets_api_client import NuggetsApiClient
from langchain_nuggets.langgraph.token_verifier import NuggetsAuthError, NuggetsTokenVerifier


class NuggetsAuth:
    """Pre-configured LangGraph Auth provider backed by Nuggets OIDC.

    Verifies bearer tokens from the Nuggets OIDC provider and returns
    user identity information to LangGraph. Optionally enriches the user
    dict with KYC verification status from the Nuggets partner API.

    Usage::

        from langchain_nuggets.langgraph import NuggetsAuth

        nuggets_auth = NuggetsAuth(
            issuer_url="https://oidc.nuggets.life",
        )
        auth = nuggets_auth.auth  # pass to langgraph.json

    Or with environment variables::

        # Set NUGGETS_OIDC_ISSUER_URL, optionally NUGGETS_API_URL etc.
        nuggets_auth = NuggetsAuth()
        auth = nuggets_auth.auth
    """

    def __init__(
        self,
        issuer_url: Optional[str] = None,
        api_url: Optional[str] = None,
        partner_id: Optional[str] = None,
        partner_secret: Optional[str] = None,
        audience: Optional[str] = None,
        require_kyc: bool = False,
        ca_cert: Optional[str] = None,
        verify_ssl: bool = True,
    ) -> None:
        resolved_issuer = issuer_url or os.environ.get("NUGGETS_OIDC_ISSUER_URL", "")
        if not resolved_issuer:
            raise ValueError(
                "NuggetsAuth requires issuer_url. "
                "Pass it explicitly or set NUGGETS_OIDC_ISSUER_URL."
            )

        self._require_kyc = require_kyc
        self._verifier = NuggetsTokenVerifier(
            issuer_url=resolved_issuer,
            audience=audience,
            ca_cert=ca_cert,
            verify_ssl=verify_ssl,
        )

        # Optional: NuggetsApiClient for KYC status enrichment
        resolved_api_url = api_url or os.environ.get("NUGGETS_API_URL", "")
        resolved_partner_id = partner_id or os.environ.get("NUGGETS_PARTNER_ID", "")
        resolved_partner_secret = partner_secret or os.environ.get("NUGGETS_PARTNER_SECRET", "")

        self._api_client: Optional[NuggetsApiClient] = None
        if resolved_api_url and resolved_partner_id and resolved_partner_secret:
            self._api_client = NuggetsApiClient({
                "api_url": resolved_api_url,
                "partner_id": resolved_partner_id,
                "partner_secret": resolved_partner_secret,
                "ca_cert": ca_cert,
                "verify_ssl": verify_ssl,
            })

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

        Extracts the bearer token, verifies it via OIDC, optionally
        enriches with KYC status, and returns a MinimalUserDict.
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

        # Build user dict from OIDC claims
        user_dict: Dict[str, Any] = {
            "identity": claims["sub"],
            "is_authenticated": True,
            "permissions": claims.get("scope", "").split() if isinstance(claims.get("scope"), str) else claims.get("scope", []),
        }

        # Copy standard OIDC claims
        for field in ("email", "name", "given_name", "family_name"):
            if field in claims:
                user_dict[field] = claims[field]

        # Copy scopes for downstream authorization helpers
        user_dict["scopes"] = user_dict["permissions"]

        # Optional: enrich with KYC status from partner API
        kyc_verified = False
        if self._api_client:
            try:
                status = await self._api_client.aget(f"/auth/status/{claims['sub']}")
                kyc_verified = bool(status.get("kyc_verified") or status.get("kycVerified"))
            except Exception:
                # KYC enrichment is best-effort — don't fail auth
                pass

        user_dict["kyc_verified"] = kyc_verified

        # Enforce KYC requirement if configured
        if self._require_kyc and not kyc_verified:
            raise Auth.exceptions.HTTPException(
                status_code=403,
                detail="KYC verification required",
            )

        return user_dict
