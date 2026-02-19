"""Tests for middleware type definitions."""
import pytest
from pydantic import ValidationError

from langchain_nuggets.middleware.types import (
    ActionContext,
    AuthorityEvaluationRequest,
    AuthorityEvaluationResponse,
    MiddlewareConfig,
    ProofArtifact,
)


class TestMiddlewareConfig:
    def test_required_fields(self):
        config = MiddlewareConfig(
            api_url="https://api.nuggets.test",
            partner_id="p-123",
            partner_secret="s-456",
            agent_id="agent-1",
            controller_id="org-1",
            delegation_id="del-1",
        )
        assert config.api_url == "https://api.nuggets.test"
        assert config.agent_id == "agent-1"

    def test_defaults(self):
        config = MiddlewareConfig(
            api_url="https://api.nuggets.test",
            partner_id="p-123",
            partner_secret="s-456",
            agent_id="agent-1",
            controller_id="org-1",
            delegation_id="del-1",
        )
        assert config.authority_endpoint == "/authority/evaluate"
        assert config.on_proof is None

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            MiddlewareConfig(
                api_url="https://api.nuggets.test",
                partner_id="p-123",
                # missing partner_secret, agent_id, etc.
            )


class TestActionContext:
    def test_serialization(self):
        ctx = ActionContext(
            tool="stripe_payment",
            target="stripe",
            parameters_hash="abc123",
            intent="Pay invoice",
            timestamp="2026-02-18T10:45:00Z",
        )
        data = ctx.model_dump()
        assert data["tool"] == "stripe_payment"
        assert data["target"] == "stripe"
        assert data["parameters_hash"] == "abc123"
        assert data["intent"] == "Pay invoice"

    def test_optional_fields(self):
        ctx = ActionContext(
            tool="lookup",
            parameters_hash="def456",
            timestamp="2026-02-18T10:45:00Z",
        )
        assert ctx.target is None
        assert ctx.intent is None


class TestAuthorityEvaluationRequest:
    def test_nested_structure(self):
        req = AuthorityEvaluationRequest(
            agent_id="agent-123",
            controller_id="org-456",
            delegation_id="del-789",
            action=ActionContext(
                tool="external_api_call",
                target="stripe",
                parameters_hash="abc123",
                intent="Pay supplier",
                timestamp="2026-02-18T10:45:00Z",
            ),
        )
        data = req.model_dump()
        assert data["agent_id"] == "agent-123"
        assert data["action"]["tool"] == "external_api_call"
        assert data["action"]["target"] == "stripe"


class TestAuthorityEvaluationResponse:
    def test_allow_response(self):
        resp = AuthorityEvaluationResponse(
            decision="ALLOW",
            proof_id="proof-xyz",
            signature="sig-abc",
        )
        assert resp.decision == "ALLOW"
        assert resp.reason_code is None

    def test_deny_response_with_reason(self):
        resp = AuthorityEvaluationResponse(
            decision="DENY",
            proof_id="proof-xyz",
            signature="sig-abc",
            reason_code="POLICY_VIOLATION",
        )
        assert resp.decision == "DENY"
        assert resp.reason_code == "POLICY_VIOLATION"

    def test_invalid_decision_raises(self):
        with pytest.raises(ValidationError):
            AuthorityEvaluationResponse(
                decision="MAYBE",
                proof_id="proof-xyz",
                signature="sig-abc",
            )


class TestProofArtifact:
    def test_all_fields(self):
        proof = ProofArtifact(
            proof_id="proof-001",
            agent_id="agent-1",
            controller_id="org-1",
            delegation_id="del-1",
            tool="stripe_payment",
            parameters_hash="abc123",
            result_hash="def456",
            authority_signature="sig-789",
            timestamp="2026-02-18T10:45:00Z",
            latency_ms=42.5,
        )
        assert proof.proof_id == "proof-001"
        assert proof.latency_ms == 42.5
        assert proof.authority_signature == "sig-789"
