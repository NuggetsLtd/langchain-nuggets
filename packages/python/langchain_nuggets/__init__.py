"""Nuggets authority middleware for LangChain / LangGraph."""
from typing import Any

from langchain_nuggets.middleware import (
    MiddlewareConfig,
    NuggetsAuthorityMiddleware,
    ProofArtifact,
)

__all__ = [
    "NuggetsAuthorityMiddleware",
    "MiddlewareConfig",
    "ProofArtifact",
]

# LangGraph Platform auth (optional — requires langgraph-sdk).
# Conditionally expose; without the extra installed, accessing these names
# raises a clear ImportError instead of an opaque AttributeError.
try:
    from langchain_nuggets.langgraph import NuggetsAuth, NuggetsAuthError

    __all__.extend(["NuggetsAuth", "NuggetsAuthError"])
except ImportError:
    _LANGGRAPH_NAMES = {"NuggetsAuth", "NuggetsAuthError"}

    def __getattr__(name: str) -> Any:
        if name in _LANGGRAPH_NAMES:
            raise ImportError(
                f"{name} requires the langgraph extra. "
                "Install with: pip install langchain-nuggets[langgraph]"
            )
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
