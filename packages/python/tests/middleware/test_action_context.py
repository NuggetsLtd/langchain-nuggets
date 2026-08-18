"""Frozen JS/Python/backend interop vectors for ACP action binding v1."""
import pytest

from langchain_nuggets.middleware.action_context import (
    compute_action_context_hash_v1,
    hash_intent_v1,
    hash_parameters_v1,
)
from langchain_nuggets.middleware.types import ActionContext, AuthorityEvaluationRequest


def _request(action: ActionContext, delegation_id: str) -> AuthorityEvaluationRequest:
    return AuthorityEvaluationRequest(
        agent_id="did:web:a",
        controller_id="did:web:c",
        delegation_id=delegation_id,
        action=action,
    )


def test_frozen_full_payment_vector() -> None:
    value = AuthorityEvaluationRequest(
        agent_id="did:web:agent.example",
        controller_id="did:web:controller.example",
        delegation_id="7",
        action=ActionContext(
            tool="nuggets.payment.send",
            target="acct_123",
            parameters_hash="a" * 64,
            intent_hash="285d9d1bfc0501e36164a9f01aa63f6ac1b178b1a8163f87a58976b143f83331",
            amount_minor=4200,
            currency="GBP",
            timestamp="excluded",
            nonce="excluded",
        ),
    )
    assert compute_action_context_hash_v1(
        value, environment="production", agent_version="1.4.0"
    ) == "a2451c2a946c4d74eea3ac7cbde24d79a4ee1013adaba418e221ccde0554e491"


def test_frozen_zero_amount_vector() -> None:
    value = _request(
        ActionContext(
            tool="refund",
            parameters_hash="d" * 64,
            amount_minor=0,
            currency="USD",
            timestamp="excluded",
            nonce="excluded",
        ),
        "42",
    )
    assert compute_action_context_hash_v1(
        value
    ) == "2665a9b78f32716f6537d98073971ee0654a29910637fd4f46b7e44c236d5e7d"


def test_intent_and_decimal_parameter_vectors() -> None:
    assert hash_intent_v1(
        "pay invoice 42"
    ) == "285d9d1bfc0501e36164a9f01aa63f6ac1b178b1a8163f87a58976b143f83331"
    assert hash_intent_v1(
        'café — π ☃ \n "q"'
    ) == "8721494a1b2e22cced778a94ef86183160d43d28de4af0b0fb64ec0b7b17579b"
    assert hash_parameters_v1(
        {"quantity": 1.5, "label": "café"}
    ) == "734b0e8e8dc237d27ceaa0c8965cf213a0451f3effc2bb99d8a7b48dc91481d8"


def test_rejects_alternate_delegation_and_unsafe_parameters() -> None:
    action = ActionContext(
        tool="t", parameters_hash="f" * 64, timestamp="excluded", nonce="excluded"
    )
    with pytest.raises(ValueError, match="delegation_id"):
        compute_action_context_hash_v1(_request(action, "042"))
    with pytest.raises(ValueError, match="unsafe"):
        hash_parameters_v1({"value": 2**53})
    with pytest.raises(ValueError, match="non-finite"):
        hash_parameters_v1({"value": float("nan")})
