"""Nuggets identity verification toolkit for LangChain."""
from langchain_nuggets.toolkit import NuggetsToolkit
from langchain_nuggets.client.nuggets_api_client import (
    NuggetsApiClient,
    NuggetsApiClientError,
)
from langchain_nuggets.tools.base import NuggetsBaseTool

# KYC tools
from langchain_nuggets.tools.kyc import (
    InitiateKycVerification,
    CheckKycStatus,
    VerifyAge,
    VerifyCredential,
)

# KYA tools
from langchain_nuggets.tools.kya import (
    RegisterAgentIdentity,
    VerifyAgentIdentity,
    GetAgentTrustScore,
)

# Auth tools
from langchain_nuggets.tools.auth import (
    RequestCredentialPresentation,
    VerifyPresentation,
    InitiateOAuthFlow,
    CheckAuthStatus,
)

__all__ = [
    # Toolkit
    "NuggetsToolkit",
    # Client
    "NuggetsApiClient",
    "NuggetsApiClientError",
    # Base
    "NuggetsBaseTool",
    # KYC
    "InitiateKycVerification",
    "CheckKycStatus",
    "VerifyAge",
    "VerifyCredential",
    # KYA
    "RegisterAgentIdentity",
    "VerifyAgentIdentity",
    "GetAgentTrustScore",
    # Auth
    "RequestCredentialPresentation",
    "VerifyPresentation",
    "InitiateOAuthFlow",
    "CheckAuthStatus",
]
