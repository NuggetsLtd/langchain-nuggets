"""Tests for consumer-side authority proof verification (#161)."""
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
    averify_authority_proof,
    verify_authority_proof,
)

PORTAL_HOST = "auth-dev.test"
PORTAL_ID = "portalClient123"
PORTAL_ISS = f"did:web:{PORTAL_HOST}:{PORTAL_ID}"
DID_URL = f"https://{PORTAL_HOST}/{PORTAL_ID}/.well-known/did.json"
KID = "portal-key-1"


@pytest.fixture(scope="module")
def portal_key():
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_jwk = json.loads(RSAAlgorithm.to_jwk(priv.public_key()))
    public_jwk["kid"] = KID
    public_jwk["alg"] = "RS256"
    return {"priv": priv, "public_jwk": public_jwk}


def _did_document(public_jwk):
    return {
        "id": PORTAL_ISS,
        "verificationMethod": [
            {
                "id": f"{PORTAL_ISS}#{KID}",
                "type": "JsonWebKey2020",
                "controller": PORTAL_ISS,
                "publicKeyJwk": public_jwk,
            }
        ],
    }


def _sign_proof(priv, claims, kid=KID):
    payload = {
        "proof_id": "proof-1",
        "agent_id": "did:web:auth-dev.test:agent1",
        "controller_id": "did:web:auth-dev.test:ctrl1",
        "delegation_id": "10",
        "action_context_hash": "abc",
        "intent_hash": None,
        "constraints_evaluated": ["not_revoked", "tool_allowed"],
        "decision": "ALLOW",
        "iat": int(time.time()),
        "iss": PORTAL_ISS,
    }
    payload.update(claims)
    pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    return jwt.encode(payload, pem, algorithm="RS256", headers={"kid": kid})


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
def test_valid_proof_verifies(portal_key):
    respx.get(DID_URL).mock(return_value=Response(200, json=_did_document(portal_key["public_jwk"])))
    sig = _sign_proof(portal_key["priv"], {})
    claims = verify_authority_proof(sig, expected=_expected())
    assert claims["proof_id"] == "proof-1"
    assert claims["decision"] == "ALLOW"


@respx.mock
def test_decision_mismatch_rejected(portal_key):
    respx.get(DID_URL).mock(return_value=Response(200, json=_did_document(portal_key["public_jwk"])))
    sig = _sign_proof(portal_key["priv"], {"decision": "ALLOW"})
    # caller expected a DENY but got an ALLOW-signed proof
    with pytest.raises(ProofVerificationError, match="decision mismatch"):
        verify_authority_proof(sig, expected=_expected(decision="DENY"))


@respx.mock
def test_proof_id_swap_rejected(portal_key):
    respx.get(DID_URL).mock(return_value=Response(200, json=_did_document(portal_key["public_jwk"])))
    sig = _sign_proof(portal_key["priv"], {"proof_id": "proof-from-another-call"})
    with pytest.raises(ProofVerificationError, match="proof_id mismatch"):
        verify_authority_proof(sig, expected=_expected())


@respx.mock
def test_agent_swap_rejected(portal_key):
    respx.get(DID_URL).mock(return_value=Response(200, json=_did_document(portal_key["public_jwk"])))
    sig = _sign_proof(portal_key["priv"], {"agent_id": "did:web:auth-dev.test:someone-else"})
    with pytest.raises(ProofVerificationError, match="agent_id mismatch"):
        verify_authority_proof(sig, expected=_expected())


@respx.mock
def test_constraints_mismatch_rejected(portal_key):
    respx.get(DID_URL).mock(return_value=Response(200, json=_did_document(portal_key["public_jwk"])))
    sig = _sign_proof(portal_key["priv"], {"constraints_evaluated": ["not_revoked"]})
    with pytest.raises(ProofVerificationError, match="constraints_evaluated mismatch"):
        verify_authority_proof(sig, expected=_expected())


@respx.mock
def test_action_context_hash_mismatch_rejected(portal_key):
    respx.get(DID_URL).mock(return_value=Response(200, json=_did_document(portal_key["public_jwk"])))
    sig = _sign_proof(portal_key["priv"], {"action_context_hash": "tampered"})
    with pytest.raises(ProofVerificationError, match="action_context_hash mismatch"):
        verify_authority_proof(sig, expected=_expected(action_context_hash="abc"))


@respx.mock
def test_signature_by_non_portal_key_rejected(portal_key):
    # did.json advertises the real portal key, but the proof was signed by a
    # different (attacker) key claiming the same kid.
    respx.get(DID_URL).mock(return_value=Response(200, json=_did_document(portal_key["public_jwk"])))
    attacker = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    sig = _sign_proof(attacker, {})
    with pytest.raises(ProofVerificationError, match="signature verification failed"):
        verify_authority_proof(sig, expected=_expected())


@respx.mock
def test_did_fetch_failure_fails_closed(portal_key):
    respx.get(DID_URL).mock(return_value=Response(503))
    sig = _sign_proof(portal_key["priv"], {})
    with pytest.raises(ProofVerificationError, match="did document fetch failed"):
        verify_authority_proof(sig, expected=_expected())


@respx.mock
def test_did_nuggets_oidc_fallback_resolves(portal_key):
    # Pre-#174 issuer form: did:nuggets:oidc:<id> + oidc_issuer_url for the host.
    fallback_url = f"https://{PORTAL_HOST}/{PORTAL_ID}/.well-known/did.json"
    respx.get(fallback_url).mock(
        return_value=Response(200, json=_did_document(portal_key["public_jwk"]))
    )
    sig = _sign_proof(portal_key["priv"], {"iss": f"did:nuggets:oidc:{PORTAL_ID}"})
    claims = verify_authority_proof(
        sig, expected=_expected(), oidc_issuer_url=f"https://{PORTAL_HOST}"
    )
    assert claims["proof_id"] == "proof-1"


def test_unsupported_issuer_rejected(portal_key):
    sig = _sign_proof(portal_key["priv"], {"iss": "did:example:nope"})
    with pytest.raises(ProofVerificationError, match="unsupported proof issuer"):
        verify_authority_proof(sig, expected=_expected())


@respx.mock
def test_kid_not_in_did_document_fails_closed(portal_key):
    # did.json publishes a key under a different kid than the proof header names.
    # Copy so we don't mutate the module-scoped fixture's jwk.
    other_jwk = {**portal_key["public_jwk"], "kid": "some-other-kid"}
    respx.get(DID_URL).mock(return_value=Response(200, json=_did_document(other_jwk)))
    sig = _sign_proof(portal_key["priv"], {})  # header kid = KID
    with pytest.raises(ProofVerificationError, match="no publicKeyJwk in did document for kid"):
        verify_authority_proof(sig, expected=_expected())


@pytest.mark.asyncio
@respx.mock
async def test_async_valid_proof_verifies(portal_key):
    respx.get(DID_URL).mock(return_value=Response(200, json=_did_document(portal_key["public_jwk"])))
    sig = _sign_proof(portal_key["priv"], {})
    claims = await averify_authority_proof(sig, expected=_expected())
    assert claims["proof_id"] == "proof-1"


@pytest.mark.asyncio
@respx.mock
async def test_async_signature_by_non_portal_key_rejected(portal_key):
    respx.get(DID_URL).mock(return_value=Response(200, json=_did_document(portal_key["public_jwk"])))
    attacker = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    sig = _sign_proof(attacker, {})
    with pytest.raises(ProofVerificationError, match="signature verification failed"):
        await averify_authority_proof(sig, expected=_expected())
