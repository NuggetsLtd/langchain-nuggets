"""Nuggets identity verification toolkit for LangChain."""
from langchain_nuggets.client.nuggets_api_client import (
    NuggetsApiClient,
    NuggetsApiClientError,
)
from langchain_nuggets.toolkit import NuggetsToolkit

# Auth tools
from langchain_nuggets.tools.auth import (
    CheckAuthStatus,
    InitiateOAuthFlow,
    RequestCredentialPresentation,
    VerifyPresentation,
)
from langchain_nuggets.tools.base import NuggetsBaseTool

# KYA tools
from langchain_nuggets.tools.kya import (
    GetAgentTrustScore,
    RegisterAgentIdentity,
    VerifyAgentIdentity,
)

# KYC tools
from langchain_nuggets.tools.kyc import (
    CheckKycStatus,
    InitiateKycVerification,
    VerifyAge,
    VerifyCredential,
)

# LangGraph auth (optional — requires langgraph-sdk)
try:
    from langchain_nuggets.langgraph import NuggetsAuth, NuggetsAuthError
except ImportError:
    pass

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
    # LangGraph (optional)
    "NuggetsAuth",
    "NuggetsAuthError",
]
