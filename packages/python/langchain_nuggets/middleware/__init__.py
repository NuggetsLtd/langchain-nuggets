"""Nuggets Authority Middleware for LangChain/LangGraph tool call interception."""
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
]
