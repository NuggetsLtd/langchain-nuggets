"""Proof artifact construction and hashing utilities."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict

from langchain_nuggets.middleware.types import AuthorityEvaluationResponse, ProofArtifact


def hash_parameters(args: Dict[str, Any]) -> str:
    """Compute SHA-256 hash of tool call arguments.

    Args are canonicalized via sorted JSON serialization
    to ensure deterministic hashing regardless of key order.
    """
    canonical = json.dumps(args, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def hash_result(result: str) -> str:
    """Compute SHA-256 hash of a tool execution result string."""
    return hashlib.sha256(result.encode("utf-8")).hexdigest()


def build_proof_artifact(
    authority_response: AuthorityEvaluationResponse,
    agent_id: str,
    controller_id: str,
    delegation_id: str,
    tool: str,
    parameters_hash: str,
    result_hash: str,
    latency_ms: float,
) -> ProofArtifact:
    """Build a ProofArtifact from an authority response and execution context."""
    return ProofArtifact(
        proof_id=authority_response.proof_id,
        agent_id=agent_id,
        controller_id=controller_id,
        delegation_id=delegation_id,
        tool=tool,
        parameters_hash=parameters_hash,
        result_hash=result_hash,
        authority_signature=authority_response.signature,
        timestamp=datetime.now(timezone.utc).isoformat(),
        latency_ms=latency_ms,
    )
