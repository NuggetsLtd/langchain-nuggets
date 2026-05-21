"""Type definitions for the Nuggets Authority Middleware."""
from __future__ import annotations

import uuid
from typing import Any, Callable, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator


class MiddlewareConfig(BaseModel):
    """Configuration for NuggetsAuthorityMiddleware."""

    api_url: str
    oidc_issuer_url: Optional[str] = None
    agent_id: str
    controller_id: str
    delegation_id: str
    authority_endpoint: str = "/api/authority/evaluate"
    authority_scope: str = "authority.evaluate"
    on_proof: Optional[Callable[["ProofArtifact"], None]] = None
    intent_resolver: Optional[Callable[[str, Dict[str, Any]], Optional[str]]] = None
    ca_cert: Optional[str] = None
    verify_ssl: bool = True
    test_mode: bool = False
    agent_private_key: Optional[Union[str, Dict[str, Any]]] = None

    model_config = {"arbitrary_types_allowed": True}

    @model_validator(mode="after")
    def _validate_oidc_issuer_when_not_test_mode(self) -> "MiddlewareConfig":
        if not self.test_mode and not self.oidc_issuer_url:
            raise ValueError(
                "oidc_issuer_url is required when test_mode is False. "
                "Set it to the Nuggets OIDC provider URL (e.g. "
                "https://auth-dev.internal-nuggets.life)."
            )
        return self

    @model_validator(mode="after")
    def _validate_agent_private_key(self) -> "MiddlewareConfig":
        if self.agent_private_key is None:
            if not self.test_mode:
                raise ValueError(
                    "agent_private_key is required when test_mode is False. "
                    "Provide a PEM string, file path, or JWK dict."
                )
            return self

        # Validate eagerly so a malformed key fails at config-construction time
        # rather than mid-request. Import lazily to avoid a circular import.
        from langchain_nuggets.middleware.agent_proof import load_private_key

        load_private_key(self.agent_private_key)
        return self


class ActionContext(BaseModel):
    """Describes the tool action being evaluated."""

    tool: str
    target: Optional[str] = None
    parameters_hash: str
    intent: Optional[str] = None
    intent_hash: Optional[str] = None
    timestamp: str
    nonce: str = Field(default_factory=lambda: str(uuid.uuid4()))


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
    constraints_evaluated: List[str] = []


class ProofArtifact(BaseModel):
    """Cryptographic proof artifact emitted after an authorized tool execution."""

    proof_id: str
    agent_id: str
    controller_id: str
    delegation_id: str
    tool: str
    parameters_hash: str
    result_hash: str
    intent_hash: Optional[str] = None
    constraints_evaluated: List[str] = []
    authority_signature: str
    timestamp: str
    latency_ms: float
    test_mode: bool = False
