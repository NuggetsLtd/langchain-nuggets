"""Consumer-side verification of authority proofs (#161, RT-P1).

Every ALLOW decision from the authority endpoint carries a compact JWS
`signature` signed by the portal's key. This module verifies that signature
against the authority's **published JWKS endpoint** (`{api_url}/.well-known/
jwks.json`) — a pinned trust anchor the SDK already knows — and binds the proof
to the request/response so a valid proof from a different call can't be swapped
in.

Pinning to the JWKS endpoint (rather than resolving the proof's own `iss` DID)
closes RT-P1 with no residual: a proof signed by an attacker's key is rejected
because the key isn't in the pinned set, *regardless of what `iss` it claims* —
even if that `iss` resolves to the attacker's own valid DID. The proof's `iss`
is ignored for key selection.

A third party can verify an emitted proof artifact out-of-band by supplying the
authority's public `jwks_uri`.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm


class ProofVerificationError(Exception):
    """Raised when an authority proof fails verification. Fail closed."""


_JWKS_CACHE_TTL_SECONDS = 300
# jwks_uri -> (keys, fetched_at). Small TTL cache so we don't refetch the
# authority JWKS on every ALLOW.
_jwks_cache: Dict[str, "tuple[List[Dict[str, Any]], float]"] = {}


def _reset_jwks_cache() -> None:
    """Test hook: drop the cached JWKS."""
    _jwks_cache.clear()


def _tls_verify(verify_ssl: bool, ca_cert: Optional[str]):
    """Map verify_ssl/ca_cert to httpx's `verify` arg (matches oidc_client)."""
    if not verify_ssl:
        return False
    if ca_cert is not None:
        return ca_cert
    return True


def _cached_keys(jwks_uri: str) -> Optional[List[Dict[str, Any]]]:
    entry = _jwks_cache.get(jwks_uri)
    if entry and (time.time() - entry[1]) < _JWKS_CACHE_TTL_SECONDS:
        return entry[0]
    return None


def _store_keys(jwks_uri: str, keys: List[Dict[str, Any]]) -> None:
    _jwks_cache[jwks_uri] = (keys, time.time())


def _keys_from_response(resp: httpx.Response, jwks_uri: str) -> List[Dict[str, Any]]:
    if resp.status_code != 200:
        raise ProofVerificationError(f"JWKS fetch failed ({resp.status_code}) for {jwks_uri}")
    try:
        body = resp.json()
    except Exception as exc:
        raise ProofVerificationError(f"JWKS at {jwks_uri} is not JSON: {exc}") from exc
    keys = body.get("keys") if isinstance(body, dict) else None
    if not isinstance(keys, list) or not keys:
        raise ProofVerificationError(f"JWKS at {jwks_uri} has no keys")
    return keys


def _select_key(keys: List[Dict[str, Any]], kid: Optional[str]) -> Dict[str, Any]:
    if kid:
        for jwk in keys:
            if isinstance(jwk, dict) and jwk.get("kid") == kid:
                return jwk
        raise ProofVerificationError(f"no key in pinned JWKS for kid={kid!r}")
    if len(keys) == 1:
        return keys[0]
    raise ProofVerificationError("proof has no kid and pinned JWKS publishes multiple keys")


def _decode_header(signature: str) -> Dict[str, Any]:
    try:
        return jwt.get_unverified_header(signature)
    except Exception as exc:
        raise ProofVerificationError(f"proof is not a decodable JWS: {exc}") from exc


def _verify_against_keys(
    signature: str,
    header: Dict[str, Any],
    keys: List[Dict[str, Any]],
    expected: Dict[str, Any],
) -> Dict[str, Any]:
    public_jwk = _select_key(keys, header.get("kid"))
    public_key = RSAAlgorithm.from_jwk(json.dumps(public_jwk))
    try:
        claims = jwt.decode(signature, key=public_key, algorithms=["RS256"])
    except Exception as exc:
        raise ProofVerificationError(f"proof signature verification failed: {exc}") from exc
    _bind(claims, expected)
    return claims


def verify_authority_proof(
    signature: str,
    *,
    expected: Dict[str, Any],
    jwks_uri: str,
    http_client: Optional[httpx.Client] = None,
    verify_ssl: bool = True,
    ca_cert: Optional[str] = None,
) -> Dict[str, Any]:
    """Verify an authority proof JWS against the pinned authority JWKS.

    Fetches `jwks_uri` (cached, short TTL), selects the key by the JWS header
    `kid`, verifies the RS256 signature, and asserts the proof's claims match
    `expected` (decision, proof_id, agent_id, controller_id,
    constraints_evaluated, and — when present in both — action_context_hash).
    The proof's `iss` is ignored: the pinned endpoint is the trust anchor.

    Pass `http_client` to reuse a connection (and its TLS config); otherwise a
    one-shot client honouring `verify_ssl` / `ca_cert` is created and closed.

    Returns the verified claims on success. Raises ProofVerificationError on
    any failure — callers must treat that as DENY.
    """
    header = _decode_header(signature)
    keys = _cached_keys(jwks_uri)
    if keys is None:
        client = http_client or httpx.Client(timeout=10, verify=_tls_verify(verify_ssl, ca_cert))
        close = http_client is None
        try:
            try:
                resp = client.get(jwks_uri)
            except Exception as exc:
                raise ProofVerificationError(f"JWKS fetch failed for {jwks_uri}: {exc}") from exc
            keys = _keys_from_response(resp, jwks_uri)
        finally:
            if close:
                client.close()
        _store_keys(jwks_uri, keys)
    return _verify_against_keys(signature, header, keys, expected)


async def averify_authority_proof(
    signature: str,
    *,
    expected: Dict[str, Any],
    jwks_uri: str,
    http_client: Optional[httpx.AsyncClient] = None,
    verify_ssl: bool = True,
    ca_cert: Optional[str] = None,
) -> Dict[str, Any]:
    """Async variant of `verify_authority_proof` — fetches the JWKS with
    `httpx.AsyncClient` so it doesn't block the event loop."""
    header = _decode_header(signature)
    keys = _cached_keys(jwks_uri)
    if keys is None:
        client = http_client or httpx.AsyncClient(
            timeout=10, verify=_tls_verify(verify_ssl, ca_cert)
        )
        close = http_client is None
        try:
            try:
                resp = await client.get(jwks_uri)
            except Exception as exc:
                raise ProofVerificationError(f"JWKS fetch failed for {jwks_uri}: {exc}") from exc
            keys = _keys_from_response(resp, jwks_uri)
        finally:
            if close:
                await client.aclose()
        _store_keys(jwks_uri, keys)
    return _verify_against_keys(signature, header, keys, expected)


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
