"""Agent proof JWS signing for the authority evaluation request.

The middleware signs each /api/authority/evaluate request with an RS256 JWS
generated from the agent's private key. The Nuggets backend verifies the
signature against the agent's registered OIDC public key, proving that the
request originated from the agent that owns the DID.
"""
from __future__ import annotations

import json
import time
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
    """Normalise a private key input (PEM string, file path, or JWK dict) to PEM."""
    if isinstance(value, dict):
        key = RSAAlgorithm.from_jwk(json.dumps(value))
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

    if isinstance(value, str):
        if _is_pem(value):
            return value
        path = Path(value)
        if path.is_file():
            return path.read_text(encoding="utf-8")
        raise ValueError(
            "agent_private_key must be a PEM string, an existing file path, "
            "or a JWK dict"
        )

    raise TypeError(
        f"agent_private_key must be str or dict, got {type(value).__name__}"
    )


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
