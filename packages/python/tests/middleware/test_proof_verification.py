"""Tests for consumer-side authority proof verification (#161, RT-P1).

Discover-and-pin model: the SDK discovers the authority's `issuer` + `jwks_uri`
from `{api_url}/.well-known/authority-configuration` (anchored on the trusted
api_url host), pins `proof.iss == issuer` (the VC-idiomatic issuer check), and
verifies the JWS signature against the keys at `jwks_uri`. Closes RT-P1: an
attacker's proof is rejected at the issuer pin (foreign iss) and/or because its
key isn't at the discovered jwks_uri.
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
    _reset_caches,
    averify_authority_proof,
    discover_authority,
    verify_authority_proof,
)

API_URL = "https://accounts-dev.test"
DISCOVERY_URI = f"{API_URL}/.well-known/authority-configuration"
JWKS_URI = f"{API_URL}/.well-known/jwks.json"
ISSUER = "did:web:auth-dev.test:sUn1FcjL6CHMm-aqB_kXV"
KID = "portal-key-1"


@pytest.fixture(autouse=True)
def _clear_caches():
    _reset_caches()
    yield
    _reset_caches()


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
        "iss": ISSUER,  # matches the discovered issuer by default
    }
    payload.update(claims or {})
    headers = {"kid": kid} if kid is not None else {}
    return jwt.encode(payload, _pem(priv), algorithm="RS256", headers=headers)


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


def _verify(sig, **kw):
    return verify_authority_proof(
        sig, expected=kw.pop("expected", _expected()), issuer=ISSUER, jwks_uri=JWKS_URI, **kw
    )


# --- discovery ------------------------------------------------------------

@respx.mock
def test_discover_authority_returns_issuer_and_jwks(portal_key):
    respx.get(DISCOVERY_URI).mock(
        return_value=Response(200, json={"issuer": ISSUER, "jwks_uri": JWKS_URI})
    )
    issuer, jwks_uri = discover_authority(API_URL)
    assert issuer == ISSUER
    assert jwks_uri == JWKS_URI


@respx.mock
def test_discover_authority_cached(portal_key):
    route = respx.get(DISCOVERY_URI).mock(
        return_value=Response(200, json={"issuer": ISSUER, "jwks_uri": JWKS_URI})
    )
    discover_authority(API_URL)
    discover_authority(API_URL)
    assert route.call_count == 1


@respx.mock
def test_discover_authority_fetch_failure_fails_closed():
    respx.get(DISCOVERY_URI).mock(return_value=Response(503))
    with pytest.raises(ProofVerificationError, match="authority discovery failed"):
        discover_authority(API_URL)


@respx.mock
def test_discover_rejects_offhost_jwks_uri():
    # SSRF guard: the discovery doc must not point verification at a foreign
    # JWKS origin. jwks_uri must share scheme+host with the discovery URL.
    respx.get(DISCOVERY_URI).mock(
        return_value=Response(200, json={"issuer": ISSUER, "jwks_uri": "https://evil.test/jwks.json"})
    )
    with pytest.raises(ProofVerificationError, match="jwks_uri host"):
        discover_authority(API_URL)


@respx.mock
def test_discover_rejects_non_string_fields():
    respx.get(DISCOVERY_URI).mock(
        return_value=Response(200, json={"issuer": 123, "jwks_uri": JWKS_URI})
    )
    with pytest.raises(ProofVerificationError, match="missing issuer/jwks_uri"):
        discover_authority(API_URL)


@respx.mock
def test_issuer_pin_runs_despite_exp_claim(portal_key):
    # Pre-parse of iss must not perform exp/claim validation. A foreign-iss
    # proof carrying a (past) exp must still be rejected at the issuer pin,
    # not surface as an opaque decode error.
    respx.get(JWKS_URI).mock(return_value=Response(200, json=_jwks(portal_key["public_jwk"])))
    sig = _sign_proof(
        portal_key["priv"],
        {"iss": "did:web:attacker.test:evil", "exp": int(time.time()) - 3600},
    )
    with pytest.raises(ProofVerificationError, match="issuer mismatch"):
        _verify(sig)


@respx.mock
def test_jwks_all_non_dict_keys_clean_error(portal_key):
    respx.get(JWKS_URI).mock(return_value=Response(200, json={"keys": [123, "nope"]}))
    with pytest.raises(ProofVerificationError, match="no usable key"):
        _verify(_sign_proof(portal_key["priv"]))


# --- verification ---------------------------------------------------------

@respx.mock
def test_valid_proof_verifies(portal_key):
    respx.get(JWKS_URI).mock(return_value=Response(200, json=_jwks(portal_key["public_jwk"])))
    claims = _verify(_sign_proof(portal_key["priv"]))
    assert claims["proof_id"] == "proof-1"
    assert claims["decision"] == "ALLOW"


@respx.mock
def test_issuer_mismatch_rejected_even_with_valid_key(portal_key):
    # C3b: signed by the REAL portal key, but the proof's iss has been tampered.
    # Pin must reject it before/independent of the signature being valid.
    respx.get(JWKS_URI).mock(return_value=Response(200, json=_jwks(portal_key["public_jwk"])))
    sig = _sign_proof(portal_key["priv"], {"iss": "did:web:attacker.test:evil"})
    with pytest.raises(ProofVerificationError, match="issuer mismatch"):
        _verify(sig)


@respx.mock
def test_attacker_key_with_pinned_iss_rejected(portal_key):
    # RT-P1: attacker copies the expected iss but signs with their own key —
    # rejected because the key isn't in the discovered jwks.
    respx.get(JWKS_URI).mock(return_value=Response(200, json=_jwks(portal_key["public_jwk"])))
    attacker = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    sig = _sign_proof(attacker)  # iss == ISSUER, but wrong key
    with pytest.raises(ProofVerificationError, match="signature verification failed"):
        _verify(sig)


@respx.mock
def test_jwks_fetch_failure_fails_closed(portal_key):
    respx.get(JWKS_URI).mock(return_value=Response(503))
    with pytest.raises(ProofVerificationError, match="JWKS fetch failed"):
        _verify(_sign_proof(portal_key["priv"]))


@respx.mock
def test_kid_no_match_falls_back_to_all_keys(portal_key):
    # Proof header names an unknown kid, but its key IS published — fall back to
    # trying all keys (rotation / kid-less). Verifies.
    respx.get(JWKS_URI).mock(return_value=Response(200, json=_jwks(portal_key["public_jwk"])))
    sig = _sign_proof(portal_key["priv"], kid="unknown-kid")
    assert _verify(sig)["decision"] == "ALLOW"


@respx.mock
def test_no_kid_falls_back_to_all_keys(portal_key):
    respx.get(JWKS_URI).mock(return_value=Response(200, json=_jwks(portal_key["public_jwk"])))
    sig = _sign_proof(portal_key["priv"], kid=None)
    assert _verify(sig)["decision"] == "ALLOW"


@respx.mock
def test_rotated_key_in_published_set_verifies(portal_key):
    retired = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    retired_jwk = json.loads(RSAAlgorithm.to_jwk(retired.public_key()))
    retired_jwk.update({"kid": "retired-k0", "alg": "RS256"})
    respx.get(JWKS_URI).mock(
        return_value=Response(200, json=_jwks(retired_jwk, portal_key["public_jwk"]))
    )
    sig = _sign_proof(retired, kid="retired-k0")
    assert _verify(sig)["decision"] == "ALLOW"


@respx.mock
def test_decision_mismatch_rejected(portal_key):
    respx.get(JWKS_URI).mock(return_value=Response(200, json=_jwks(portal_key["public_jwk"])))
    with pytest.raises(ProofVerificationError, match="decision mismatch"):
        _verify(_sign_proof(portal_key["priv"]), expected=_expected(decision="DENY"))


@respx.mock
def test_proof_id_swap_rejected(portal_key):
    respx.get(JWKS_URI).mock(return_value=Response(200, json=_jwks(portal_key["public_jwk"])))
    with pytest.raises(ProofVerificationError, match="proof_id mismatch"):
        _verify(_sign_proof(portal_key["priv"], {"proof_id": "another-call"}))


@respx.mock
def test_constraints_mismatch_rejected(portal_key):
    respx.get(JWKS_URI).mock(return_value=Response(200, json=_jwks(portal_key["public_jwk"])))
    with pytest.raises(ProofVerificationError, match="constraints_evaluated mismatch"):
        _verify(_sign_proof(portal_key["priv"], {"constraints_evaluated": ["not_revoked"]}))


@respx.mock
def test_jwks_cached_across_calls(portal_key):
    route = respx.get(JWKS_URI).mock(
        return_value=Response(200, json=_jwks(portal_key["public_jwk"]))
    )
    sig = _sign_proof(portal_key["priv"])
    _verify(sig)
    _verify(sig)
    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_async_valid_proof_verifies(portal_key):
    respx.get(JWKS_URI).mock(return_value=Response(200, json=_jwks(portal_key["public_jwk"])))
    claims = await averify_authority_proof(
        _sign_proof(portal_key["priv"]), expected=_expected(), issuer=ISSUER, jwks_uri=JWKS_URI
    )
    assert claims["proof_id"] == "proof-1"


@pytest.mark.asyncio
@respx.mock
async def test_async_issuer_mismatch_rejected(portal_key):
    respx.get(JWKS_URI).mock(return_value=Response(200, json=_jwks(portal_key["public_jwk"])))
    sig = _sign_proof(portal_key["priv"], {"iss": "did:web:attacker.test:evil"})
    with pytest.raises(ProofVerificationError, match="issuer mismatch"):
        await averify_authority_proof(
            sig, expected=_expected(), issuer=ISSUER, jwks_uri=JWKS_URI
        )
