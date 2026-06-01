"""Consumer-side verification of authority proofs (#161, RT-P1).

Discover-and-pin model. Every ALLOW decision carries a compact JWS `signature`
signed by the authority. The SDK:

1. **Discovers** the authority's `issuer` + `jwks_uri` from
   `{api_url}/.well-known/authority-configuration` — anchored on the trusted
   `api_url` host, so nothing is baked per environment.
2. **Pins the issuer**: `proof.iss == issuer` (the discovered value). This uses
   `iss` the VC-idiomatic way — a pinned comparison against the expected
   authority, NOT resolve-and-trust.
3. **Verifies the signature** against the keys at `jwks_uri` (by JWS header
   `kid`, falling back to trying all published keys — covers rotation / kid-less
   keys).
4. Binds the proof to the request/response (decision, proof_id, agent_id,
   controller_id, constraints_evaluated) and fails closed on any problem.

This closes RT-P1 with no residual and no per-env secret: an attacker's proof is
rejected at the issuer pin (foreign `iss`) and/or because its key isn't at the
discovered `jwks_uri`. A third party can verify an emitted proof out-of-band by
discovering the same endpoint (or supplying the known `issuer` + `jwks_uri`).
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm


class ProofVerificationError(Exception):
    """Raised when an authority proof fails verification. Fail closed."""


_CACHE_TTL_SECONDS = 300
# Small TTL caches so we don't refetch discovery / JWKS on every ALLOW.
_discovery_cache: Dict[str, Tuple[Tuple[str, str], float]] = {}  # api_url -> ((issuer, jwks_uri), t)
_jwks_cache: Dict[str, Tuple[List[Dict[str, Any]], float]] = {}  # jwks_uri -> (keys, t)


def _reset_caches() -> None:
    """Test hook: drop cached discovery + JWKS."""
    _discovery_cache.clear()
    _jwks_cache.clear()


def _tls_verify(verify_ssl: bool, ca_cert: Optional[str]):
    """Map verify_ssl/ca_cert to httpx's `verify` arg (matches oidc_client)."""
    if not verify_ssl:
        return False
    if ca_cert is not None:
        return ca_cert
    return True


def _fresh(entry, ttl: float = _CACHE_TTL_SECONDS) -> bool:
    return entry is not None and (time.time() - entry[1]) < ttl


# --- discovery ------------------------------------------------------------

def _discovery_url(api_url: str) -> str:
    return f"{api_url.rstrip('/')}/.well-known/authority-configuration"


def _parse_discovery(resp: httpx.Response, url: str) -> Tuple[str, str]:
    if resp.status_code != 200:
        raise ProofVerificationError(f"authority discovery failed ({resp.status_code}) for {url}")
    try:
        body = resp.json()
    except Exception as exc:
        raise ProofVerificationError(f"authority discovery at {url} is not JSON: {exc}") from exc
    issuer = body.get("issuer") if isinstance(body, dict) else None
    jwks_uri = body.get("jwks_uri") if isinstance(body, dict) else None
    if not issuer or not jwks_uri:
        raise ProofVerificationError(
            f"authority discovery at {url} missing issuer/jwks_uri"
        )
    return issuer, jwks_uri


def discover_authority(
    api_url: str,
    *,
    http_client: Optional[httpx.Client] = None,
    verify_ssl: bool = True,
    ca_cert: Optional[str] = None,
) -> Tuple[str, str]:
    """Discover the authority's (issuer, jwks_uri) from
    `{api_url}/.well-known/authority-configuration`. Cached, fail-closed."""
    cached = _discovery_cache.get(api_url)
    if _fresh(cached):
        return cached[0]
    url = _discovery_url(api_url)
    client = http_client or httpx.Client(timeout=10, verify=_tls_verify(verify_ssl, ca_cert))
    close = http_client is None
    try:
        try:
            resp = client.get(url)
        except Exception as exc:
            raise ProofVerificationError(f"authority discovery failed for {url}: {exc}") from exc
        result = _parse_discovery(resp, url)
    finally:
        if close:
            client.close()
    _discovery_cache[api_url] = (result, time.time())
    return result


async def adiscover_authority(
    api_url: str,
    *,
    http_client: Optional[httpx.AsyncClient] = None,
    verify_ssl: bool = True,
    ca_cert: Optional[str] = None,
) -> Tuple[str, str]:
    """Async variant of `discover_authority`."""
    cached = _discovery_cache.get(api_url)
    if _fresh(cached):
        return cached[0]
    url = _discovery_url(api_url)
    client = http_client or httpx.AsyncClient(timeout=10, verify=_tls_verify(verify_ssl, ca_cert))
    close = http_client is None
    try:
        try:
            resp = await client.get(url)
        except Exception as exc:
            raise ProofVerificationError(f"authority discovery failed for {url}: {exc}") from exc
        result = _parse_discovery(resp, url)
    finally:
        if close:
            await client.aclose()
    _discovery_cache[api_url] = (result, time.time())
    return result


# --- jwks fetch + verification --------------------------------------------

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


def _candidate_keys(keys: List[Dict[str, Any]], kid: Optional[str]) -> List[Dict[str, Any]]:
    """Keys to try, kid-match first, then the rest (rotation / kid-less)."""
    keys = [k for k in keys if isinstance(k, dict)]
    if kid:
        matched = [k for k in keys if k.get("kid") == kid]
        rest = [k for k in keys if k.get("kid") != kid]
        return matched + rest
    return keys


def _decode_header(signature: str) -> Dict[str, Any]:
    try:
        return jwt.get_unverified_header(signature)
    except Exception as exc:
        raise ProofVerificationError(f"proof is not a decodable JWS: {exc}") from exc


def _unverified_iss(signature: str) -> str:
    try:
        iss = jwt.decode(signature, options={"verify_signature": False}).get("iss")
    except Exception as exc:
        raise ProofVerificationError(f"proof is not a decodable JWS: {exc}") from exc
    if not iss:
        raise ProofVerificationError("proof has no iss claim")
    return iss


def _verify_signature_against_keys(
    signature: str, keys: List[Dict[str, Any]], kid: Optional[str]
) -> Dict[str, Any]:
    last_err: Optional[Exception] = None
    for jwk in _candidate_keys(keys, kid):
        try:
            public_key = RSAAlgorithm.from_jwk(json.dumps(jwk))
            return jwt.decode(signature, key=public_key, algorithms=["RS256"])
        except Exception as exc:  # try the next published key
            last_err = exc
    raise ProofVerificationError(f"proof signature verification failed: {last_err}")


def _verify_core(
    signature: str, expected: Dict[str, Any], issuer: str, keys: List[Dict[str, Any]]
) -> Dict[str, Any]:
    # 1. Pin the issuer (VC-idiomatic) before trusting anything else.
    iss = _unverified_iss(signature)
    if iss != issuer:
        raise ProofVerificationError(f"proof issuer mismatch: proof={iss!r} expected={issuer!r}")
    # 2. Verify the signature against the discovered key set.
    header = _decode_header(signature)
    claims = _verify_signature_against_keys(signature, keys, header.get("kid"))
    # 3. Bind to the request/response.
    _bind(claims, expected)
    return claims


def verify_authority_proof(
    signature: str,
    *,
    expected: Dict[str, Any],
    issuer: str,
    jwks_uri: str,
    http_client: Optional[httpx.Client] = None,
    verify_ssl: bool = True,
    ca_cert: Optional[str] = None,
) -> Dict[str, Any]:
    """Verify an authority proof: pin `iss == issuer`, verify the RS256
    signature against the keys at `jwks_uri`, and bind the claims to `expected`.

    `issuer` and `jwks_uri` come from the authority's discovery document (see
    `discover_authority`). Pass `http_client` to reuse a connection (and its TLS
    config); otherwise a one-shot client honouring `verify_ssl`/`ca_cert` is
    created and closed.

    Returns the verified claims on success. Raises ProofVerificationError on any
    failure — callers must treat that as DENY.
    """
    keys = _jwks_cache.get(jwks_uri)
    if _fresh(keys):
        return _verify_core(signature, expected, issuer, keys[0])
    client = http_client or httpx.Client(timeout=10, verify=_tls_verify(verify_ssl, ca_cert))
    close = http_client is None
    try:
        try:
            resp = client.get(jwks_uri)
        except Exception as exc:
            raise ProofVerificationError(f"JWKS fetch failed for {jwks_uri}: {exc}") from exc
        key_list = _keys_from_response(resp, jwks_uri)
    finally:
        if close:
            client.close()
    _jwks_cache[jwks_uri] = (key_list, time.time())
    return _verify_core(signature, expected, issuer, key_list)


async def averify_authority_proof(
    signature: str,
    *,
    expected: Dict[str, Any],
    issuer: str,
    jwks_uri: str,
    http_client: Optional[httpx.AsyncClient] = None,
    verify_ssl: bool = True,
    ca_cert: Optional[str] = None,
) -> Dict[str, Any]:
    """Async variant of `verify_authority_proof` — fetches the JWKS with
    `httpx.AsyncClient` so it doesn't block the event loop."""
    keys = _jwks_cache.get(jwks_uri)
    if _fresh(keys):
        return _verify_core(signature, expected, issuer, keys[0])
    client = http_client or httpx.AsyncClient(timeout=10, verify=_tls_verify(verify_ssl, ca_cert))
    close = http_client is None
    try:
        try:
            resp = await client.get(jwks_uri)
        except Exception as exc:
            raise ProofVerificationError(f"JWKS fetch failed for {jwks_uri}: {exc}") from exc
        key_list = _keys_from_response(resp, jwks_uri)
    finally:
        if close:
            await client.aclose()
    _jwks_cache[jwks_uri] = (key_list, time.time())
    return _verify_core(signature, expected, issuer, key_list)


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
