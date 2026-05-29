"""Consumer-side verification of authority proofs (#161).

Every ALLOW decision from the authority endpoint carries a compact JWS
`signature` signed by the portal's key. This module verifies that signature
against the portal's published key — resolved from the proof's own `iss`
DID — and binds the proof to the request/response so a valid proof from a
different call can't be swapped in.

This is what makes an authority decision *independently verifiable*: a third
party can call `verify_authority_proof()` on an emitted proof artifact with no
Nuggets-specific knowledge beyond generic did:web resolution.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm


class ProofVerificationError(Exception):
    """Raised when an authority proof fails verification. Fail closed."""


def _issuer_did_to_did_url(iss: str, oidc_issuer_url: Optional[str]) -> str:
    """Resolve a proof issuer DID to its did.json URL.

    - ``did:web:<host>:<...>:<id>`` → ``https://<host>/<id>/.well-known/did.json``
      (generic did:web resolution — host + id come straight from the DID).
    - ``did:nuggets:oidc:<id>`` → fallback for environments still on the
      pre-#174 proof issuer: derive the host from ``oidc_issuer_url``.
    """
    if iss.startswith("did:web:"):
        parts = iss.split(":")
        if len(parts) < 3:
            raise ProofVerificationError(f"malformed did:web issuer: {iss}")
        host = parts[2]
        client_id = parts[-1]
        return f"https://{host}/{client_id}/.well-known/did.json"
    if iss.startswith("did:nuggets:oidc:"):
        if not oidc_issuer_url:
            raise ProofVerificationError(
                "proof issuer is did:nuggets:oidc but no oidc_issuer_url given for fallback"
            )
        host = httpx.URL(oidc_issuer_url).host
        client_id = iss[len("did:nuggets:oidc:"):]
        return f"https://{host}/{client_id}/.well-known/did.json"
    raise ProofVerificationError(f"unsupported proof issuer DID: {iss}")


def _public_jwk_for_kid(did_document: Dict[str, Any], kid: Optional[str]) -> Dict[str, Any]:
    methods = did_document.get("verificationMethod") or []
    jwks = [m.get("publicKeyJwk") for m in methods if isinstance(m, dict) and m.get("publicKeyJwk")]
    if not jwks:
        raise ProofVerificationError("did document has no verificationMethod publicKeyJwk")
    if kid:
        for jwk in jwks:
            if jwk.get("kid") == kid:
                return jwk
    return jwks[0]


def verify_authority_proof(
    signature: str,
    *,
    expected: Dict[str, Any],
    oidc_issuer_url: Optional[str] = None,
    http_client: Optional[httpx.Client] = None,
) -> Dict[str, Any]:
    """Verify an authority proof JWS and bind it to the expected decision.

    Resolves the signing key from the proof's `iss` DID (did:web), verifies
    the RS256 signature, then asserts the proof's claims match `expected`
    (decision, proof_id, agent_id, controller_id, constraints_evaluated, and —
    when present in both — action_context_hash).

    Returns the verified claims on success. Raises ProofVerificationError on
    any failure — callers must treat that as DENY.
    """
    try:
        header = jwt.get_unverified_header(signature)
        unverified = jwt.decode(signature, options={"verify_signature": False})
    except Exception as exc:
        raise ProofVerificationError(f"proof is not a decodable JWS: {exc}") from exc

    iss = unverified.get("iss")
    if not iss:
        raise ProofVerificationError("proof has no iss claim")

    did_url = _issuer_did_to_did_url(iss, oidc_issuer_url)
    client = http_client or httpx.Client(timeout=10)
    close = http_client is None
    try:
        resp = client.get(did_url)
    except Exception as exc:
        raise ProofVerificationError(f"could not resolve proof issuer {did_url}: {exc}") from exc
    finally:
        if close:
            client.close()
    if resp.status_code != 200:
        raise ProofVerificationError(
            f"did document fetch failed ({resp.status_code}) for {did_url}"
        )

    public_jwk = _public_jwk_for_kid(resp.json(), header.get("kid"))
    public_key = RSAAlgorithm.from_jwk(json.dumps(public_jwk))

    try:
        claims = jwt.decode(signature, key=public_key, algorithms=["RS256"])
    except Exception as exc:
        raise ProofVerificationError(f"proof signature verification failed: {exc}") from exc

    _bind(claims, expected)
    return claims


def _bind(claims: Dict[str, Any], expected: Dict[str, Any]) -> None:
    def check(field: str) -> None:
        if field in expected and claims.get(field) != expected[field]:
            raise ProofVerificationError(
                f"proof {field} mismatch: proof={claims.get(field)!r} expected={expected[field]!r}"
            )

    for field in ("decision", "proof_id", "agent_id", "controller_id", "action_context_hash"):
        check(field)

    if "constraints_evaluated" in expected:
        proof_c: List[str] = claims.get("constraints_evaluated") or []
        if list(proof_c) != list(expected["constraints_evaluated"]):
            raise ProofVerificationError(
                "proof constraints_evaluated mismatch: "
                f"proof={proof_c!r} expected={expected['constraints_evaluated']!r}"
            )
