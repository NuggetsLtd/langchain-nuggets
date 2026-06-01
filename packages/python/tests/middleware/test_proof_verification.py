"""Tests for consumer-side authority proof verification (#161, RT-P1).

Verification is pinned to the authority's published JWKS endpoint
(`{api_url}/.well-known/jwks.json`). The proof's claimed `iss` is ignored
for key selection — the pinned endpoint is the trust anchor — so an
attacker-signed proof is rejected even if its `iss` resolves to the
attacker's own valid DID (RT-P1).
"""
import json
import time

import jwt
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import Response
from jwt.algorithms import RSAAlgorithm

from langchain_nuggets.middleware.proof_verification import (
    ProofVerificationError,
    _reset_jwks_cache,
    averify_authority_proof,
    verify_authority_proof,
)

API_URL = "https://accounts-dev.test"
JWKS_URI = f"{API_URL}/.well-known/jwks.json"
KID = "portal-key-1"


@pytest.fixture(autouse=True)
def _clear_cache():
    _reset_jwks_cache()
    yield
    _reset_jwks_cache()


@pytest.fixture(scope="module")
def portal_key():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(RSAAlgorithm.to_jwk(priv.public_key()))
    public_jwk["kid"] = KID
    public_jwk["alg"] = "RS256"
    return {"priv": priv, "public_jwk": public_jwk}


def _jwks(*public_jwks):
    return {"keys": list(public_jwks)}


def _pem(priv):
    return priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


def _sign_proof(priv, claims=None, kid=KID):
    payload = {
        "proof_id": "proof-1",
        "agent_id": "did:web:auth-dev.test:agent1",
        "controller_id": "did:web:auth-dev.test:ctrl1",
        "delegation_id": "10",
        "constraints_evaluated": ["not_revoked", "tool_allowed"],
        "decision": "ALLOW",
        "iat": int(time.time()),
        # An issuer the verifier must IGNORE for key selection.
        "iss": "did:web:auth-dev.test:sUn1FcjL6CHMm-aqB_kXV",
    }
    payload.update(claims or {})
    return jwt.encode(payload, _pem(priv), algorithm="RS256", headers={"kid": kid})


def _expected(**overrides):
    exp = {
        "decision": "ALLOW",
        "proof_id": "proof-1",
        "agent_id": "did:web:auth-dev.test:agent1",
        "controller_id": "did:web:auth-dev.test:ctrl1",
        "constraints_evaluated": ["not_revoked", "tool_allowed"],
    }
    exp.update(overrides)
    return exp


@respx.mock
def test_valid_proof_verifies_against_pinned_jwks(portal_key):
    respx.get(JWKS_URI).mock(return_value=Response(200, json=_jwks(portal_key["public_jwk"])))
    sig = _sign_proof(portal_key["priv"])
    claims = verify_authority_proof(sig, expected=_expected(), jwks_uri=JWKS_URI)
    assert claims["proof_id"] == "proof-1"
    assert claims["decision"] == "ALLOW"


@respx.mock
def test_attacker_signed_with_resolvable_iss_rejected(portal_key):
    # RT-P1: the proof is signed by an attacker key and its iss would resolve to
    # the attacker's own valid DID — but the key isn't in the pinned JWKS, so it
    # must be rejected regardless of iss.
    respx.get(JWKS_URI).mock(return_value=Response(200, json=_jwks(portal_key["public_jwk"])))
    attacker = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    sig = _sign_proof(attacker, {"iss": "did:web:attacker.test:evil"})
    with pytest.raises(ProofVerificationError, match="no key in pinned JWKS|signature verification failed"):
        verify_authority_proof(sig, expected=_expected(), jwks_uri=JWKS_URI)


@respx.mock
def test_jwks_fetch_failure_fails_closed(portal_key):
    respx.get(JWKS_URI).mock(return_value=Response(503))
    sig = _sign_proof(portal_key["priv"])
    with pytest.raises(ProofVerificationError, match="JWKS fetch failed"):
        verify_authority_proof(sig, expected=_expected(), jwks_uri=JWKS_URI)


@respx.mock
def test_rotated_key_in_published_set_verifies(portal_key):
    # JWKS publishes a retired key plus the current signing key; a proof signed
    # by either verifies.
    retired = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    retired_jwk = json.loads(RSAAlgorithm.to_jwk(retired.public_key()))
    retired_jwk.update({"kid": "retired-k0", "alg": "RS256"})
    respx.get(JWKS_URI).mock(
        return_value=Response(200, json=_jwks(retired_jwk, portal_key["public_jwk"]))
    )
    sig = _sign_proof(retired, kid="retired-k0")
    claims = verify_authority_proof(sig, expected=_expected(), jwks_uri=JWKS_URI)
    assert claims["decision"] == "ALLOW"


@respx.mock
def test_kid_not_in_jwks_fails_closed(portal_key):
    respx.get(JWKS_URI).mock(return_value=Response(200, json=_jwks(portal_key["public_jwk"])))
    sig = _sign_proof(portal_key["priv"], kid="some-other-kid")
    with pytest.raises(ProofVerificationError, match="no key in pinned JWKS"):
        verify_authority_proof(sig, expected=_expected(), jwks_uri=JWKS_URI)


@respx.mock
def test_decision_mismatch_rejected(portal_key):
    respx.get(JWKS_URI).mock(return_value=Response(200, json=_jwks(portal_key["public_jwk"])))
    sig = _sign_proof(portal_key["priv"])
    with pytest.raises(ProofVerificationError, match="decision mismatch"):
        verify_authority_proof(sig, expected=_expected(decision="DENY"), jwks_uri=JWKS_URI)


@respx.mock
def test_proof_id_swap_rejected(portal_key):
    respx.get(JWKS_URI).mock(return_value=Response(200, json=_jwks(portal_key["public_jwk"])))
    sig = _sign_proof(portal_key["priv"], {"proof_id": "another-call"})
    with pytest.raises(ProofVerificationError, match="proof_id mismatch"):
        verify_authority_proof(sig, expected=_expected(), jwks_uri=JWKS_URI)


@respx.mock
def test_constraints_mismatch_rejected(portal_key):
    respx.get(JWKS_URI).mock(return_value=Response(200, json=_jwks(portal_key["public_jwk"])))
    sig = _sign_proof(portal_key["priv"], {"constraints_evaluated": ["not_revoked"]})
    with pytest.raises(ProofVerificationError, match="constraints_evaluated mismatch"):
        verify_authority_proof(sig, expected=_expected(), jwks_uri=JWKS_URI)


@respx.mock
def test_jwks_cached_across_calls(portal_key):
    route = respx.get(JWKS_URI).mock(
        return_value=Response(200, json=_jwks(portal_key["public_jwk"]))
    )
    sig = _sign_proof(portal_key["priv"])
    verify_authority_proof(sig, expected=_expected(), jwks_uri=JWKS_URI)
    verify_authority_proof(sig, expected=_expected(), jwks_uri=JWKS_URI)
    assert route.call_count == 1  # second call served from cache


@pytest.mark.asyncio
@respx.mock
async def test_async_valid_proof_verifies(portal_key):
    respx.get(JWKS_URI).mock(return_value=Response(200, json=_jwks(portal_key["public_jwk"])))
    sig = _sign_proof(portal_key["priv"])
    claims = await averify_authority_proof(sig, expected=_expected(), jwks_uri=JWKS_URI)
    assert claims["proof_id"] == "proof-1"


@pytest.mark.asyncio
@respx.mock
async def test_async_attacker_signed_rejected(portal_key):
    respx.get(JWKS_URI).mock(return_value=Response(200, json=_jwks(portal_key["public_jwk"])))
    attacker = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    sig = _sign_proof(attacker)
    with pytest.raises(ProofVerificationError):
        await averify_authority_proof(sig, expected=_expected(), jwks_uri=JWKS_URI)
