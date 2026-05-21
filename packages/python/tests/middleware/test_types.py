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
            agent_id="agent-1",
            controller_id="org-1",
            delegation_id="del-1",
            test_mode=True,
        )
        assert config.api_url == "https://api.nuggets.test"
        assert config.agent_id == "agent-1"

    def test_defaults(self):
        config = MiddlewareConfig(
            api_url="https://api.nuggets.test",
            agent_id="agent-1",
            controller_id="org-1",
            delegation_id="del-1",
            test_mode=True,
        )
        assert config.authority_endpoint == "/api/authority/evaluate"
        assert config.on_proof is None

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            MiddlewareConfig(
                api_url="https://api.nuggets.test",
                # missing agent_id, controller_id, delegation_id, etc.
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

    def test_nonce_auto_generated(self):
        ctx = ActionContext(
            tool="lookup",
            parameters_hash="def456",
            timestamp="2026-02-18T10:45:00Z",
        )
        assert ctx.nonce
        assert len(ctx.nonce) == 36  # uuid4 with dashes

    def test_nonce_unique_per_instance(self):
        ctx1 = ActionContext(tool="t", parameters_hash="h", timestamp="2026-02-18T10:45:00Z")
        ctx2 = ActionContext(tool="t", parameters_hash="h", timestamp="2026-02-18T10:45:00Z")
        assert ctx1.nonce != ctx2.nonce

    def test_nonce_serialized(self):
        ctx = ActionContext(tool="t", parameters_hash="h", timestamp="2026-02-18T10:45:00Z")
        assert ctx.model_dump()["nonce"] == ctx.nonce

    def test_nonce_can_be_overridden(self):
        ctx = ActionContext(
            tool="t",
            parameters_hash="h",
            timestamp="2026-02-18T10:45:00Z",
            nonce="custom-nonce-value",
        )
        assert ctx.nonce == "custom-nonce-value"


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


class TestMiddlewareConfigTls:
    def test_tls_defaults(self):
        config = MiddlewareConfig(
            api_url="https://api.test",
            agent_id="a",
            controller_id="c",
            delegation_id="d",
            test_mode=True,
        )
        assert config.ca_cert is None
        assert config.verify_ssl is True

    def test_with_ca_cert(self):
        config = MiddlewareConfig(
            api_url="https://api.test",
            agent_id="a",
            controller_id="c",
            delegation_id="d",
            ca_cert="/path/ca.pem",
            test_mode=True,
        )
        assert config.ca_cert == "/path/ca.pem"


class TestMiddlewareConfigAgentProof:
    def _base_kwargs(self):
        return dict(
            api_url="https://api.test",
            oidc_issuer_url="https://auth.test",
            agent_id="a",
            controller_id="c",
            delegation_id="d",
        )

    def test_test_mode_allows_missing_key(self):
        config = MiddlewareConfig(**self._base_kwargs(), test_mode=True)
        assert config.agent_private_key is None

    def test_non_test_mode_requires_key(self):
        with pytest.raises(ValidationError) as exc_info:
            MiddlewareConfig(**self._base_kwargs())
        assert "agent_private_key" in str(exc_info.value)

    def test_pem_string_accepted(self):
        pem = "-----BEGIN RSA PRIVATE KEY-----\nABC\n-----END RSA PRIVATE KEY-----"
        config = MiddlewareConfig(**self._base_kwargs(), agent_private_key=pem)
        assert config.agent_private_key == pem

    def test_jwk_dict_accepted(self):
        # Valid private JWK (generated via cryptography lib at test time)
        import json as _json

        from cryptography.hazmat.primitives.asymmetric import rsa
        from jwt.algorithms import RSAAlgorithm

        priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk = _json.loads(RSAAlgorithm.to_jwk(priv))
        config = MiddlewareConfig(**self._base_kwargs(), agent_private_key=jwk)
        assert config.agent_private_key == jwk

    def test_public_jwk_rejected(self):
        import json as _json

        from cryptography.hazmat.primitives.asymmetric import rsa
        from jwt.algorithms import RSAAlgorithm

        priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_jwk = _json.loads(RSAAlgorithm.to_jwk(priv.public_key()))
        with pytest.raises(ValidationError) as exc_info:
            MiddlewareConfig(**self._base_kwargs(), agent_private_key=public_jwk)
        assert "private" in str(exc_info.value)

    def test_bogus_string_rejected(self):
        with pytest.raises(ValidationError):
            MiddlewareConfig(
                **self._base_kwargs(),
                agent_private_key="not-a-pem-not-a-path",
            )
