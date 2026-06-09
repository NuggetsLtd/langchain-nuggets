"""Nuggets Authority Middleware for LangChain/LangGraph tool call interception."""
from typing import Any

from langchain_nuggets.middleware.authority_middleware import NuggetsAuthorityMiddleware
from langchain_nuggets.middleware.proof import build_proof_artifact, hash_parameters, hash_result
from langchain_nuggets.middleware.proof_verification import (
    ProofVerificationError,
    adiscover_authority,
    averify_authority_proof,
    discover_authority,
    verify_authority_proof,
)
from langchain_nuggets.middleware.types import (
    ActionContext,
    AuthorityDecision,
    AuthorityEvaluationRequest,
    AuthorityEvaluationResponse,
    MiddlewareConfig,
    ProofArtifact,
)

__all__ = [
    "NuggetsAuthorityMiddleware",
    "MiddlewareConfig",
    "ActionContext",
    "AuthorityDecision",
    "AuthorityEvaluationRequest",
    "AuthorityEvaluationResponse",
    "ProofArtifact",
    "build_proof_artifact",
    "hash_parameters",
    "hash_result",
    "verify_authority_proof",
    "averify_authority_proof",
    "discover_authority",
    "adiscover_authority",
    "ProofVerificationError",
    "NuggetsAuthorityAgentMiddleware",
]


def __getattr__(name: str) -> Any:
    # NuggetsAuthorityAgentMiddleware needs langchain (>=1.0), an optional
    # dependency. Import lazily so langchain-core-only installs aren't forced to
    # pull langchain, and surface a clear install hint when it's missing.
    if name == "NuggetsAuthorityAgentMiddleware":
        try:
            from langchain_nuggets.middleware.agent_middleware import (
                NuggetsAuthorityAgentMiddleware,
            )
        except ImportError as exc:  # pragma: no cover - exercised via extras
            raise ImportError(
                "NuggetsAuthorityAgentMiddleware requires langchain>=1.0. "
                "Install it with: pip install langchain-nuggets[agent]"
            ) from exc
        return NuggetsAuthorityAgentMiddleware
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
