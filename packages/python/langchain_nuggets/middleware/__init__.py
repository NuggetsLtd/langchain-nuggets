"""Nuggets Authority Middleware for LangChain/LangGraph tool call interception."""
from langchain_nuggets.middleware.authority_middleware import NuggetsAuthorityMiddleware
from langchain_nuggets.middleware.proof import build_proof_artifact, hash_parameters, hash_result
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
]
