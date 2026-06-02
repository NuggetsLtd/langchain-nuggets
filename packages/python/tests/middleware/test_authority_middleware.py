"""Tests for NuggetsAuthorityMiddleware."""
import json
import time
from unittest.mock import AsyncMock, MagicMock

import jwt
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import Response
from jwt.algorithms import RSAAlgorithm
from langchain_core.messages import ToolMessage

from langchain_nuggets.middleware.authority_middleware import NuggetsAuthorityMiddleware
from langchain_nuggets.middleware.proof import hash_parameters
from langchain_nuggets.middleware.types import MiddlewareConfig


@pytest.fixture(scope="module")
def rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
    return {"private_pem": private_pem, "public_pem": public_pem}


@pytest.fixture
def config(rsa_keypair):
    # verify_proofs is off here: these tests exercise routing/proof-emission
    # mechanics with a stub signature and predate #161. Proof verification has
    # its own dedicated coverage in TestProofVerificationDefaultOn (which flips
    # it back on) and in test_proof_verification.py.
    return MiddlewareConfig(
        api_url="https://api.nuggets.test",
        oidc_issuer_url="https://auth.nuggets.test",
        agent_id="agent-123",
        controller_id="org-456",
        delegation_id="del-789",
        agent_private_key=rsa_keypair["private_pem"],
        verify_proofs=False,
    )


@pytest.fixture
def allow_response():
    return {
        "decision": "ALLOW",
        "proof_id": "proof-xyz",
        "signature": "sig-abc",
        "reason_code": None,
        "constraints_evaluated": ["tool_allowed", "target_allowed", "cap_remaining"],
    }


@pytest.fixture
def deny_response():
    return {
        "decision": "DENY",
        "proof_id": "proof-xyz",
        "signature": "sig-abc",
        "reason_code": "POLICY_VIOLATION",
    }


@pytest.fixture
def mock_request():
    request = MagicMock()
    request.tool_call = {
        "name": "external_api_call",
        "args": {"target": "stripe", "amount": 100},
        "id": "call-123",
    }
    return request


@pytest.fixture
def mock_handler():
    handler = MagicMock()
    handler.return_value = ToolMessage(
        content='{"status": "success", "id": "txn-456"}',
        tool_call_id="call-123",
    )
    return handler


@pytest.fixture
def mock_async_handler():
    handler = AsyncMock()
    handler.return_value = ToolMessage(
        content='{"status": "success", "id": "txn-456"}',
        tool_call_id="call-123",
    )
    return handler


class TestExtractOidcClientId:
    def test_strips_did_nuggets_oidc_prefix(self):
        from langchain_nuggets.middleware.authority_middleware import _extract_oidc_client_id

        assert _extract_oidc_client_id("did:nuggets:oidc:sUn1Fcj") == "sUn1Fcj"

    def test_returns_last_segment_of_did_web(self):
        from langchain_nuggets.middleware.authority_middleware import _extract_oidc_client_id

        did = "did:web:auth-dev.internal-nuggets.life:WhWeJ30e5"
        assert _extract_oidc_client_id(did) == "WhWeJ30e5"

    def test_did_web_with_path_segments(self):
        from langchain_nuggets.middleware.authority_middleware import _extract_oidc_client_id

        did = "did:web:auth.nuggets.life:agents:org-1:WhWeJ30e5"
        assert _extract_oidc_client_id(did) == "WhWeJ30e5"

    def test_did_web_too_short_returns_unchanged(self):
        from langchain_nuggets.middleware.authority_middleware import _extract_oidc_client_id

        assert _extract_oidc_client_id("did:web:example.com") == "did:web:example.com"

    def test_bare_id_returned_unchanged(self):
        from langchain_nuggets.middleware.authority_middleware import _extract_oidc_client_id

        assert _extract_oidc_client_id("WhWeJ30e5") == "WhWeJ30e5"

    def test_unknown_did_method_returned_unchanged(self):
        from langchain_nuggets.middleware.authority_middleware import _extract_oidc_client_id

        assert _extract_oidc_client_id("did:key:abc123") == "did:key:abc123"


class TestConstruction:
    def test_create_middleware(self, config):
        middleware = NuggetsAuthorityMiddleware(config)
        assert middleware is not None

    def test_proofs_initially_empty(self, config):
        middleware = NuggetsAuthorityMiddleware(config)
        assert middleware.proofs == []


class TestProofVerificationDefaultOn:
    """#161: the SDK verifies the authority proof by default and fails closed."""

    def test_allow_with_unverifiable_signature_fails_closed(
        self, config, allow_response, mock_request, mock_handler
    ):
        # Flip verification back on (the shared fixture disables it). The fake
        # "sig-abc" isn't a decodable JWS, so verification must fail and the
        # ALLOW must be downgraded to PROOF_VERIFICATION_FAILED — tool NOT run.
        config = config.model_copy(update={"verify_proofs": True})
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.post.return_value = allow_response

        result = middleware.wrap_tool_call(mock_request, mock_handler)

        mock_handler.assert_not_called()
        data = json.loads(result.content)
        assert data["status"] == "DENIED"
        assert data["reason_code"] == "PROOF_VERIFICATION_FAILED"
        assert middleware.proofs == []

    def test_explicit_opt_out_skips_verification(
        self, config, allow_response, mock_request, mock_handler
    ):
        # Shared config has verify_proofs=False; the unverifiable sig passes.
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.post.return_value = allow_response

        result = middleware.wrap_tool_call(mock_request, mock_handler)

        mock_handler.assert_called_once()
        assert "success" in result.content

    def test_test_mode_skips_verification(self, rsa_keypair, mock_request, mock_handler):
        # test_mode proofs are intentionally unverifiable; verification is skipped.
        cfg = MiddlewareConfig(
            api_url="https://api.nuggets.test",
            agent_id="agent-123",
            controller_id="org-456",
            delegation_id="del-789",
            test_mode=True,
            verify_proofs=True,
        )
        middleware = NuggetsAuthorityMiddleware(cfg)
        result = middleware.wrap_tool_call(mock_request, mock_handler)
        mock_handler.assert_called_once()
        assert "success" in result.content

    @respx.mock
    def test_verifiable_proof_passes_through(self, rsa_keypair, mock_request, mock_handler):
        from langchain_nuggets.middleware.proof_verification import _reset_caches

        _reset_caches()
        kid = "portal-k1"
        issuer = "did:web:auth.nuggets.test:portalC1"
        portal = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_jwk = json.loads(RSAAlgorithm.to_jwk(portal.public_key()))
        public_jwk.update({"kid": kid, "alg": "RS256"})
        # The middleware discovers issuer+jwks_uri, then verifies against jwks.
        respx.get("https://api.nuggets.test/.well-known/authority-configuration").mock(
            return_value=Response(
                200,
                json={
                    "issuer": issuer,
                    "jwks_uri": "https://api.nuggets.test/.well-known/jwks.json",
                },
            )
        )
        respx.get("https://api.nuggets.test/.well-known/jwks.json").mock(
            return_value=Response(200, json={"keys": [public_jwk]})
        )
        portal_pem = portal.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()
        proof_jws = jwt.encode(
            {
                "proof_id": "proof-real",
                "agent_id": "agent-123",
                "controller_id": "org-456",
                "constraints_evaluated": ["tool_allowed"],
                "decision": "ALLOW",
                "iat": int(time.time()),
                "iss": issuer,
            },
            portal_pem,
            algorithm="RS256",
            headers={"kid": kid},
        )
        cfg = MiddlewareConfig(
            api_url="https://api.nuggets.test",
            oidc_issuer_url="https://auth.nuggets.test",
            agent_id="agent-123",
            controller_id="org-456",
            delegation_id="del-789",
            agent_private_key=rsa_keypair["private_pem"],
            verify_proofs=True,
        )
        middleware = NuggetsAuthorityMiddleware(cfg)
        middleware._client = MagicMock()
        middleware._client.post.return_value = {
            "decision": "ALLOW",
            "proof_id": "proof-real",
            "signature": proof_jws,
            "reason_code": None,
            "constraints_evaluated": ["tool_allowed"],
        }
        result = middleware.wrap_tool_call(mock_request, mock_handler)
        mock_handler.assert_called_once()
        assert "success" in result.content
        assert len(middleware.proofs) == 1


class TestSyncWrapToolCall:
    def test_allow_executes_tool(self, config, allow_response, mock_request, mock_handler):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.post.return_value = allow_response

        result = middleware.wrap_tool_call(mock_request, mock_handler)

        mock_handler.assert_called_once_with(mock_request)
        assert isinstance(result, ToolMessage)
        assert "success" in result.content

    def test_allow_emits_proof(self, config, allow_response, mock_request, mock_handler):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.post.return_value = allow_response

        middleware.wrap_tool_call(mock_request, mock_handler)

        assert len(middleware.proofs) == 1
        proof = middleware.proofs[0]
        assert proof.proof_id == "proof-xyz"
        assert proof.agent_id == "agent-123"
        assert proof.tool == "external_api_call"
        assert proof.authority_signature == "sig-abc"

    def test_deny_blocks_tool(self, config, deny_response, mock_request, mock_handler):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.post.return_value = deny_response

        result = middleware.wrap_tool_call(mock_request, mock_handler)

        mock_handler.assert_not_called()
        assert isinstance(result, ToolMessage)
        data = json.loads(result.content)
        assert data["status"] == "DENIED"
        assert data["tool"] == "external_api_call"

    def test_deny_includes_reason(self, config, deny_response, mock_request, mock_handler):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.post.return_value = deny_response

        result = middleware.wrap_tool_call(mock_request, mock_handler)

        data = json.loads(result.content)
        assert data["reason_code"] == "POLICY_VIOLATION"

    def test_error_fails_closed(self, config, mock_request, mock_handler):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.post.side_effect = ConnectionError("Network error")

        result = middleware.wrap_tool_call(mock_request, mock_handler)

        mock_handler.assert_not_called()
        assert isinstance(result, ToolMessage)
        data = json.loads(result.content)
        assert data["status"] == "ERROR"
        assert "Network error" in data["message"]

    def test_proof_callback_invoked(self, config, allow_response, mock_request, mock_handler):
        callback = MagicMock()
        config_with_cb = config.model_copy(update={"on_proof": callback})
        middleware = NuggetsAuthorityMiddleware(config_with_cb)
        middleware._client = MagicMock()
        middleware._client.post.return_value = allow_response

        middleware.wrap_tool_call(mock_request, mock_handler)

        callback.assert_called_once()
        proof = callback.call_args[0][0]
        assert proof.proof_id == "proof-xyz"

    def test_parameters_hash_in_eval_request(self, config, allow_response, mock_request, mock_handler):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.post.return_value = allow_response

        middleware.wrap_tool_call(mock_request, mock_handler)

        call_args = middleware._client.post.call_args
        payload = call_args[0][1]
        expected_hash = hash_parameters({"target": "stripe", "amount": 100})
        assert payload["action"]["parameters_hash"] == expected_hash

    def test_multiple_calls_accumulate_proofs(self, config, allow_response, mock_request, mock_handler):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.post.return_value = allow_response

        middleware.wrap_tool_call(mock_request, mock_handler)
        middleware.wrap_tool_call(mock_request, mock_handler)
        middleware.wrap_tool_call(mock_request, mock_handler)

        assert len(middleware.proofs) == 3

    def test_latency_tracking(self, config, allow_response, mock_request, mock_handler):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.post.return_value = allow_response

        middleware.wrap_tool_call(mock_request, mock_handler)

        proof = middleware.proofs[0]
        assert proof.latency_ms > 0

    def test_idempotency_key_sent_as_header(
        self, config, allow_response, mock_request, mock_handler
    ):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.post.return_value = allow_response

        middleware.wrap_tool_call(mock_request, mock_handler)

        kwargs = middleware._client.post.call_args.kwargs
        assert "headers" in kwargs
        assert "Idempotency-Key" in kwargs["headers"]
        assert len(kwargs["headers"]["Idempotency-Key"]) == 36  # uuid4

    def test_idempotency_key_unique_per_call(
        self, config, allow_response, mock_request, mock_handler
    ):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.post.return_value = allow_response

        middleware.wrap_tool_call(mock_request, mock_handler)
        middleware.wrap_tool_call(mock_request, mock_handler)

        keys = [
            call.kwargs["headers"]["Idempotency-Key"]
            for call in middleware._client.post.call_args_list
        ]
        assert keys[0] != keys[1]

    def test_nonce_sent_in_action_payload(
        self, config, allow_response, mock_request, mock_handler
    ):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.post.return_value = allow_response

        middleware.wrap_tool_call(mock_request, mock_handler)

        payload = middleware._client.post.call_args.args[1]
        assert "nonce" in payload["action"]
        assert len(payload["action"]["nonce"]) == 36

    def test_nonce_unique_per_call(
        self, config, allow_response, mock_request, mock_handler
    ):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.post.return_value = allow_response

        middleware.wrap_tool_call(mock_request, mock_handler)
        middleware.wrap_tool_call(mock_request, mock_handler)

        nonces = [
            call.args[1]["action"]["nonce"]
            for call in middleware._client.post.call_args_list
        ]
        assert nonces[0] != nonces[1]


class TestAsyncWrapToolCall:
    async def test_allow_executes_tool(
        self, config, allow_response, mock_request, mock_async_handler
    ):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.apost = AsyncMock(return_value=allow_response)

        result = await middleware.awrap_tool_call(mock_request, mock_async_handler)

        mock_async_handler.assert_awaited_once_with(mock_request)
        assert isinstance(result, ToolMessage)
        assert "success" in result.content

    async def test_deny_blocks_tool(
        self, config, deny_response, mock_request, mock_async_handler
    ):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.apost = AsyncMock(return_value=deny_response)

        result = await middleware.awrap_tool_call(mock_request, mock_async_handler)

        mock_async_handler.assert_not_awaited()
        data = json.loads(result.content)
        assert data["status"] == "DENIED"

    async def test_error_fails_closed(self, config, mock_request, mock_async_handler):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.apost = AsyncMock(side_effect=ConnectionError("Network error"))

        result = await middleware.awrap_tool_call(mock_request, mock_async_handler)

        mock_async_handler.assert_not_awaited()
        data = json.loads(result.content)
        assert data["status"] == "ERROR"

    async def test_allow_emits_proof(
        self, config, allow_response, mock_request, mock_async_handler
    ):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.apost = AsyncMock(return_value=allow_response)

        await middleware.awrap_tool_call(mock_request, mock_async_handler)

        assert len(middleware.proofs) == 1
        assert middleware.proofs[0].proof_id == "proof-xyz"

    async def test_idempotency_key_sent_as_header_async(
        self, config, allow_response, mock_request, mock_async_handler
    ):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.apost = AsyncMock(return_value=allow_response)

        await middleware.awrap_tool_call(mock_request, mock_async_handler)

        kwargs = middleware._client.apost.call_args.kwargs
        assert "Idempotency-Key" in kwargs["headers"]

    async def test_nonce_sent_in_action_payload_async(
        self, config, allow_response, mock_request, mock_async_handler
    ):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.apost = AsyncMock(return_value=allow_response)

        await middleware.awrap_tool_call(mock_request, mock_async_handler)

        payload = middleware._client.apost.call_args.args[1]
        assert "nonce" in payload["action"]


class TestMiddlewareTls:
    def test_threads_tls_to_client(self, rsa_keypair):
        config = MiddlewareConfig(
            api_url="https://api.test",
            oidc_issuer_url="https://auth.test",
            agent_id="a",
            controller_id="c",
            delegation_id="d",
            ca_cert="/path/ca.pem",
            agent_private_key=rsa_keypair["private_pem"],
        )
        middleware = NuggetsAuthorityMiddleware(config)
        assert middleware._client is not None
        assert middleware._client._verify == "/path/ca.pem"


class TestIntentBinding:
    def test_intent_hash_in_proof_when_intent_resolver_set(
        self, config, allow_response, mock_request, mock_handler
    ):
        config_with_intent = config.model_copy(
            update={"intent_resolver": lambda tool, args: "transfer funds to user"}
        )
        middleware = NuggetsAuthorityMiddleware(config_with_intent)
        middleware._client = MagicMock()
        middleware._client.post.return_value = allow_response

        middleware.wrap_tool_call(mock_request, mock_handler)

        proof = middleware.proofs[0]
        assert proof.intent_hash is not None
        assert len(proof.intent_hash) == 64  # SHA-256 hex

    def test_no_intent_hash_without_resolver(
        self, config, allow_response, mock_request, mock_handler
    ):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.post.return_value = allow_response

        middleware.wrap_tool_call(mock_request, mock_handler)

        proof = middleware.proofs[0]
        assert proof.intent_hash is None

    def test_different_intent_different_proof_hash(
        self, config, allow_response, mock_request, mock_handler
    ):
        """Same tool + same args + different intent → different intent_hash in proof."""
        intents = iter(["transfer funds", "check balance"])
        config_with_intent = config.model_copy(
            update={"intent_resolver": lambda tool, args: next(intents)}
        )
        middleware = NuggetsAuthorityMiddleware(config_with_intent)
        middleware._client = MagicMock()
        middleware._client.post.return_value = allow_response

        middleware.wrap_tool_call(mock_request, mock_handler)
        middleware.wrap_tool_call(mock_request, mock_handler)

        proof1, proof2 = middleware.proofs
        assert proof1.intent_hash != proof2.intent_hash

    def test_intent_hash_sent_in_eval_request(
        self, config, allow_response, mock_request, mock_handler
    ):
        config_with_intent = config.model_copy(
            update={"intent_resolver": lambda tool, args: "transfer funds"}
        )
        middleware = NuggetsAuthorityMiddleware(config_with_intent)
        middleware._client = MagicMock()
        middleware._client.post.return_value = allow_response

        middleware.wrap_tool_call(mock_request, mock_handler)

        payload = middleware._client.post.call_args[0][1]
        assert payload["action"]["intent_hash"] is not None
        assert payload["action"]["intent"] == "transfer funds"


class TestConstraintsEvaluated:
    def test_constraints_in_proof(
        self, config, allow_response, mock_request, mock_handler
    ):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.post.return_value = allow_response

        middleware.wrap_tool_call(mock_request, mock_handler)

        proof = middleware.proofs[0]
        assert proof.constraints_evaluated == ["tool_allowed", "target_allowed", "cap_remaining"]

    def test_empty_constraints_when_not_provided(
        self, config, mock_request, mock_handler
    ):
        response_no_constraints = {
            "decision": "ALLOW",
            "proof_id": "proof-xyz",
            "signature": "sig-abc",
            "reason_code": None,
        }
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.post.return_value = response_no_constraints

        middleware.wrap_tool_call(mock_request, mock_handler)

        proof = middleware.proofs[0]
        assert proof.constraints_evaluated == []

    async def test_constraints_in_async_proof(
        self, config, allow_response, mock_request, mock_async_handler
    ):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.apost = AsyncMock(return_value=allow_response)

        await middleware.awrap_tool_call(mock_request, mock_async_handler)

        proof = middleware.proofs[0]
        assert proof.constraints_evaluated == ["tool_allowed", "target_allowed", "cap_remaining"]


class TestTestMode:
    @pytest.fixture
    def test_mode_config(self):
        return MiddlewareConfig(
            api_url="https://unreachable.invalid",
            agent_id="agent-test",
            controller_id="org-test",
            delegation_id="del-test",
            test_mode=True,
        )

    def test_sync_skips_http_call(self, test_mode_config, mock_request, mock_handler):
        middleware = NuggetsAuthorityMiddleware(test_mode_config)
        middleware._client = MagicMock()

        result = middleware.wrap_tool_call(mock_request, mock_handler)

        middleware._client.post.assert_not_called()
        mock_handler.assert_called_once_with(mock_request)
        assert isinstance(result, ToolMessage)

    def test_sync_proof_marked_test_mode(self, test_mode_config, mock_request, mock_handler):
        middleware = NuggetsAuthorityMiddleware(test_mode_config)
        middleware.wrap_tool_call(mock_request, mock_handler)

        proof = middleware.proofs[0]
        assert proof.test_mode is True
        assert proof.authority_signature == "test-mode-unverifiable"
        assert proof.proof_id.startswith("test-")

    def test_sync_proof_preserves_hashes_and_intent(
        self, test_mode_config, mock_request, mock_handler
    ):
        cfg = test_mode_config.model_copy(
            update={"intent_resolver": lambda tool, args: "transfer funds"}
        )
        middleware = NuggetsAuthorityMiddleware(cfg)
        middleware.wrap_tool_call(mock_request, mock_handler)

        proof = middleware.proofs[0]
        assert proof.parameters_hash == hash_parameters({"target": "stripe", "amount": 100})
        assert proof.result_hash  # non-empty
        assert proof.intent_hash is not None

    async def test_async_skips_http_call(
        self, test_mode_config, mock_request, mock_async_handler
    ):
        middleware = NuggetsAuthorityMiddleware(test_mode_config)
        middleware._client = MagicMock()
        middleware._client.apost = AsyncMock()

        result = await middleware.awrap_tool_call(mock_request, mock_async_handler)

        middleware._client.apost.assert_not_called()
        mock_async_handler.assert_awaited_once_with(mock_request)
        assert isinstance(result, ToolMessage)

    async def test_async_proof_marked_test_mode(
        self, test_mode_config, mock_request, mock_async_handler
    ):
        middleware = NuggetsAuthorityMiddleware(test_mode_config)
        await middleware.awrap_tool_call(mock_request, mock_async_handler)

        proof = middleware.proofs[0]
        assert proof.test_mode is True
        assert proof.authority_signature == "test-mode-unverifiable"

    def test_proof_callback_invoked_in_test_mode(
        self, test_mode_config, mock_request, mock_handler
    ):
        callback = MagicMock()
        cfg = test_mode_config.model_copy(update={"on_proof": callback})
        middleware = NuggetsAuthorityMiddleware(cfg)

        middleware.wrap_tool_call(mock_request, mock_handler)

        callback.assert_called_once()
        assert callback.call_args[0][0].test_mode is True

    def test_default_is_not_test_mode(self, config):
        assert config.test_mode is False


class TestAgentProof:
    def test_agent_proof_field_sent_in_payload(
        self, config, allow_response, mock_request, mock_handler
    ):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.post.return_value = allow_response

        middleware.wrap_tool_call(mock_request, mock_handler)

        payload = middleware._client.post.call_args.args[1]
        assert "agent_proof" in payload
        assert isinstance(payload["agent_proof"], str)
        assert payload["agent_proof"].count(".") == 2  # JWS has three segments

    def test_agent_proof_verifies_with_public_key(
        self, config, rsa_keypair, allow_response, mock_request, mock_handler
    ):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.post.return_value = allow_response

        middleware.wrap_tool_call(mock_request, mock_handler)

        payload = middleware._client.post.call_args.args[1]
        decoded = jwt.decode(
            payload["agent_proof"],
            rsa_keypair["public_pem"],
            algorithms=["RS256"],
        )
        assert decoded["agent_id"] == config.agent_id
        assert decoded["nonce"] == payload["action"]["nonce"]
        assert "iat" in decoded
        assert "exp" in decoded
        assert decoded["exp"] > decoded["iat"]

    def test_agent_proof_fresh_per_call(
        self, config, allow_response, mock_request, mock_handler
    ):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.post.return_value = allow_response

        middleware.wrap_tool_call(mock_request, mock_handler)
        middleware.wrap_tool_call(mock_request, mock_handler)

        proofs = [
            call.args[1]["agent_proof"]
            for call in middleware._client.post.call_args_list
        ]
        assert proofs[0] != proofs[1]

    def test_jwk_dict_private_key(
        self, rsa_keypair, allow_response, mock_request, mock_handler
    ):
        # Convert PEM to JWK using PyJWT's algorithm helper
        algo = jwt.algorithms.RSAAlgorithm(jwt.algorithms.RSAAlgorithm.SHA256)
        private_key = algo.prepare_key(rsa_keypair["private_pem"])
        jwk = json.loads(algo.to_jwk(private_key))

        config = MiddlewareConfig(
            api_url="https://api.nuggets.test",
            oidc_issuer_url="https://auth.nuggets.test",
            agent_id="agent-123",
            controller_id="c",
            delegation_id="d",
            agent_private_key=jwk,
        )
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.post.return_value = allow_response

        middleware.wrap_tool_call(mock_request, mock_handler)

        payload = middleware._client.post.call_args.args[1]
        decoded = jwt.decode(
            payload["agent_proof"],
            rsa_keypair["public_pem"],
            algorithms=["RS256"],
        )
        assert decoded["agent_id"] == "agent-123"

    def test_file_path_private_key(
        self, tmp_path, rsa_keypair, allow_response, mock_request, mock_handler
    ):
        key_file = tmp_path / "agent.pem"
        key_file.write_text(rsa_keypair["private_pem"])

        config = MiddlewareConfig(
            api_url="https://api.nuggets.test",
            oidc_issuer_url="https://auth.nuggets.test",
            agent_id="agent-123",
            controller_id="c",
            delegation_id="d",
            agent_private_key=str(key_file),
        )
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.post.return_value = allow_response

        middleware.wrap_tool_call(mock_request, mock_handler)

        payload = middleware._client.post.call_args.args[1]
        assert payload["agent_proof"].count(".") == 2

    async def test_agent_proof_in_async_payload(
        self, config, allow_response, mock_request, mock_async_handler
    ):
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()
        middleware._client.apost = AsyncMock(return_value=allow_response)

        await middleware.awrap_tool_call(mock_request, mock_async_handler)

        payload = middleware._client.apost.call_args.args[1]
        assert "agent_proof" in payload
        assert payload["agent_proof"].count(".") == 2

    def test_test_mode_skips_agent_proof(
        self, mock_request, mock_handler
    ):
        config = MiddlewareConfig(
            api_url="https://unreachable.invalid",
            agent_id="agent-test",
            controller_id="c",
            delegation_id="d",
            test_mode=True,
        )
        middleware = NuggetsAuthorityMiddleware(config)
        middleware._client = MagicMock()

        # No private key set; test_mode should bypass JWS generation
        result = middleware.wrap_tool_call(mock_request, mock_handler)
        assert isinstance(result, ToolMessage)
        middleware._client.post.assert_not_called()
