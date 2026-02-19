"""Tests for proof hashing and construction utilities."""
import hashlib
import json

from langchain_nuggets.middleware.proof import (
    build_proof_artifact,
    hash_parameters,
    hash_result,
)
from langchain_nuggets.middleware.types import AuthorityEvaluationResponse


class TestHashParameters:
    def test_deterministic_regardless_of_key_order(self):
        h1 = hash_parameters({"b": 2, "a": 1})
        h2 = hash_parameters({"a": 1, "b": 2})
        assert h1 == h2

    def test_different_args_different_hash(self):
        h1 = hash_parameters({"amount": 100})
        h2 = hash_parameters({"amount": 200})
        assert h1 != h2

    def test_empty_args(self):
        h = hash_parameters({})
        expected = hashlib.sha256(b"{}").hexdigest()
        assert h == expected

    def test_known_value(self):
        args = {"key": "value"}
        canonical = json.dumps(args, sort_keys=True, separators=(",", ":"))
        expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        assert hash_parameters(args) == expected


class TestHashResult:
    def test_hash_result(self):
        result = '{"status": "success"}'
        expected = hashlib.sha256(result.encode("utf-8")).hexdigest()
        assert hash_result(result) == expected


class TestBuildProofArtifact:
    def test_builds_correct_proof(self):
        response = AuthorityEvaluationResponse(
            decision="ALLOW",
            proof_id="proof-001",
            signature="sig-abc",
        )
        proof = build_proof_artifact(
            authority_response=response,
            agent_id="agent-1",
            controller_id="org-1",
            delegation_id="del-1",
            tool="stripe_payment",
            parameters_hash="params-hash",
            result_hash="result-hash",
            latency_ms=55.3,
        )
        assert proof.proof_id == "proof-001"
        assert proof.agent_id == "agent-1"
        assert proof.authority_signature == "sig-abc"
        assert proof.tool == "stripe_payment"
        assert proof.latency_ms == 55.3
        # Timestamp should be ISO 8601 UTC
        assert "T" in proof.timestamp
        assert proof.timestamp.endswith("+00:00") or proof.timestamp.endswith("Z")
