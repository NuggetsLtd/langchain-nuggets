"""Agent proof JWS signing for the authority evaluation request.

The middleware signs each /api/authority/evaluate request with an RS256 JWS
generated from the agent's private key. The Nuggets backend verifies the
signature against the agent's registered OIDC public key, proving that the
request originated from the agent that owns the DID.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Union

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from jwt.algorithms import RSAAlgorithm

PrivateKeyInput = Union[str, Dict[str, Any]]

_PROOF_TTL_SECONDS = 300


def _is_pem(value: str) -> bool:
    return value.lstrip().startswith("-----BEGIN")


def load_private_key(value: PrivateKeyInput) -> str:
    """Normalise a private key input to PEM.

    Accepted forms:
    - PEM string (starts with `-----BEGIN`)
    - Path to a file containing PEM, a single private JWK, or a JWKS
      (`{"keys": [...]}`) — the accounts portal exports this last form
    - A `dict` containing a single private JWK or a JWKS
    """
    if isinstance(value, dict):
        return _jwk_or_jwks_dict_to_pem(value)

    if isinstance(value, str):
        if _is_pem(value):
            return value
        path = Path(value)
        if path.is_file():
            content = path.read_text(encoding="utf-8")
            stripped = content.lstrip()
            if stripped.startswith("-----BEGIN"):
                return content
            if stripped.startswith("{"):
                try:
                    parsed = json.loads(content)
                except json.JSONDecodeError as err:
                    raise ValueError(
                        f"agent_private_key file at {path} is not valid PEM or JSON: {err}"
                    ) from err
                if not isinstance(parsed, dict):
                    raise ValueError(
                        f"agent_private_key file at {path} must contain a JWK or JWKS object"
                    )
                return _jwk_or_jwks_dict_to_pem(parsed)
            raise ValueError(
                f"agent_private_key file at {path} is not PEM or JSON (JWK/JWKS)"
            )
        raise ValueError(
            "agent_private_key must be a PEM string, an existing file path, "
            "or a JWK/JWKS dict"
        )

    raise TypeError(
        f"agent_private_key must be str or dict, got {type(value).__name__}"
    )


def _jwk_or_jwks_dict_to_pem(value: Dict[str, Any]) -> str:
    """Convert a JWK or JWKS dict to PEM. JWKS takes the first key."""
    keys = value.get("keys")
    if isinstance(keys, list):
        if not keys:
            raise ValueError("agent_private_key JWKS contains no keys")
        jwk = keys[0]
        if not isinstance(jwk, dict):
            raise ValueError("agent_private_key JWKS keys[0] is not an object")
    else:
        jwk = value

    key = RSAAlgorithm.from_jwk(json.dumps(jwk))
    if not isinstance(key, RSAPrivateKey):
        raise ValueError(
            "agent_private_key JWK must be a private RSA key "
            "(missing private parameters like 'd')"
        )
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")


def sign_agent_proof(private_key_pem: str, agent_id: str, nonce: str) -> str:
    """Sign an RS256 JWS with claims {agent_id, nonce, iat, exp}."""
    now = int(time.time())
    payload = {
        "agent_id": agent_id,
        "nonce": nonce,
        "iat": now,
        "exp": now + _PROOF_TTL_SECONDS,
    }
    return jwt.encode(payload, private_key_pem, algorithm="RS256")


def sign_agent_proof_v1(
    private_key_pem: str,
    *,
    agent_id: str,
    nonce: str,
    audience: str,
    action_context_hash: str,
) -> str:
    """Sign a fresh v1 action-bound RS256 agent proof."""
    now = int(time.time())
    payload = {
        "agent_id": agent_id,
        "nonce": nonce,
        "action_context_version": 1,
        "action_context_hash": action_context_hash,
        "aud": audience,
        "iat": now,
        "exp": now + _PROOF_TTL_SECONDS,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, private_key_pem, algorithm="RS256")
