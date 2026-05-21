"""Nuggets authority middleware for LangChain / LangGraph."""
from langchain_nuggets.middleware import (
    MiddlewareConfig,
    NuggetsAuthorityMiddleware,
    ProofArtifact,
)

# LangGraph Platform auth (optional — requires langgraph-sdk)
try:
    from langchain_nuggets.langgraph import NuggetsAuth, NuggetsAuthError
except ImportError:
    pass

__all__ = [
    "NuggetsAuthorityMiddleware",
    "MiddlewareConfig",
    "ProofArtifact",
    "NuggetsAuth",
    "NuggetsAuthError",
]
