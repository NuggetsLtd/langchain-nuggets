"""Nuggets toolkit providing all identity verification tools."""
from __future__ import annotations

import os
from typing import List, Optional

from langchain_core.tools import BaseTool

from langchain_nuggets.client.nuggets_api_client import NuggetsApiClient
from langchain_nuggets.tools.kyc import (
    InitiateKycVerification,
    CheckKycStatus,
    VerifyAge,
    VerifyCredential,
)
from langchain_nuggets.tools.kya import (
    RegisterAgentIdentity,
    VerifyAgentIdentity,
    GetAgentTrustScore,
)
from langchain_nuggets.tools.auth import (
    RequestCredentialPresentation,
    VerifyPresentation,
    InitiateOAuthFlow,
    CheckAuthStatus,
)


class NuggetsToolkit:
    """Toolkit that provides all Nuggets identity verification tools.

    Config can be passed directly or read from environment variables:
    - NUGGETS_API_URL
    - NUGGETS_PARTNER_ID
    - NUGGETS_PARTNER_SECRET
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        partner_id: Optional[str] = None,
        partner_secret: Optional[str] = None,
    ) -> None:
        resolved_api_url = api_url or os.environ.get("NUGGETS_API_URL", "")
        resolved_partner_id = partner_id or os.environ.get("NUGGETS_PARTNER_ID", "")
        resolved_partner_secret = partner_secret or os.environ.get("NUGGETS_PARTNER_SECRET", "")

        if not resolved_api_url or not resolved_partner_id or not resolved_partner_secret:
            raise ValueError(
                "NuggetsToolkit requires api_url, partner_id, and partner_secret. "
                "Provide them via constructor or NUGGETS_API_URL, NUGGETS_PARTNER_ID, "
                "NUGGETS_PARTNER_SECRET environment variables."
            )

        self._client = NuggetsApiClient({
            "api_url": resolved_api_url,
            "partner_id": resolved_partner_id,
            "partner_secret": resolved_partner_secret,
        })

    def get_tools(self) -> List[BaseTool]:
        """Return all 11 Nuggets identity verification tools."""
        params = {"client": self._client}
        return [
            InitiateKycVerification(**params),
            CheckKycStatus(**params),
            VerifyAge(**params),
            VerifyCredential(**params),
            RegisterAgentIdentity(**params),
            VerifyAgentIdentity(**params),
            GetAgentTrustScore(**params),
            RequestCredentialPresentation(**params),
            VerifyPresentation(**params),
            InitiateOAuthFlow(**params),
            CheckAuthStatus(**params),
        ]
