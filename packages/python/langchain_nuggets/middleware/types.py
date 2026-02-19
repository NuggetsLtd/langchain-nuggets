"""Type definitions for the Nuggets Authority Middleware."""
from __future__ import annotations

from typing import Any, Callable, Literal, Optional

from pydantic import BaseModel


class MiddlewareConfig(BaseModel):
    """Configuration for NuggetsAuthorityMiddleware."""

    api_url: str
    partner_id: str
    partner_secret: str
    agent_id: str
    controller_id: str
    delegation_id: str
    authority_endpoint: str = "/authority/evaluate"
    on_proof: Optional[Any] = None  # Callable[[ProofArtifact], None]

    model_config = {"arbitrary_types_allowed": True}


class ActionContext(BaseModel):
    """Describes the tool action being evaluated."""

    tool: str
    target: Optional[str] = None
    parameters_hash: str
    intent: Optional[str] = None
    timestamp: str


class AuthorityEvaluationRequest(BaseModel):
    """Request payload sent to the Nuggets authority evaluation endpoint."""

    agent_id: str
    controller_id: str
    delegation_id: str
    action: ActionContext


AuthorityDecision = Literal["ALLOW", "DENY"]


class AuthorityEvaluationResponse(BaseModel):
    """Response from the Nuggets authority evaluation endpoint."""

    decision: AuthorityDecision
    proof_id: str
    signature: str
    reason_code: Optional[str] = None


class ProofArtifact(BaseModel):
    """Cryptographic proof artifact emitted after an authorized tool execution."""

    proof_id: str
    agent_id: str
    controller_id: str
    delegation_id: str
    tool: str
    parameters_hash: str
    result_hash: str
    authority_signature: str
    timestamp: str
    latency_ms: float
