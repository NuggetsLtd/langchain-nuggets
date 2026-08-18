"""Byte-exact ACP action-context binding (version 1)."""
from __future__ import annotations

import hashlib
import math
import re
from typing import Any, Dict, Optional

import rfc8785

from langchain_nuggets.middleware.types import AuthorityEvaluationRequest

ACTION_CONTEXT_VERSION_V1 = 1
ACTION_CONTEXT_DOMAIN_V1 = "nuggets.acp.action_context.v1"
PARAMETERS_DOMAIN_V1 = "nuggets.acp.parameters.v1"
INTENT_DOMAIN_V1 = "nuggets.acp.intent.v1"

_MAX_SAFE_INTEGER = 2**53 - 1
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
_DELEGATION_ID = re.compile(r"^[1-9][0-9]*$")


def _assert_json_value(value: Any, path: str, allow_floats: bool) -> None:
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, int):
        if abs(value) > _MAX_SAFE_INTEGER:
            raise ValueError(f"unsafe integer at {path}")
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"non-finite number at {path}")
        if not allow_floats:
            raise ValueError(f"non-integer number at {path}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _assert_json_value(item, f"{path}[{index}]", allow_floats)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"non-string object key at {path}")
            _assert_json_value(item, f"{path}.{key}", allow_floats)
        return
    raise ValueError(f"unsupported value at {path}")


def _hash_jcs(domain: str, value: Any, *, allow_floats: bool) -> str:
    _assert_json_value(value, "$", allow_floats)
    canonical = rfc8785.dumps(value)
    return hashlib.sha256(domain.encode("utf-8") + b"\n" + canonical).hexdigest()


def hash_parameters_v1(parameters: Dict[str, Any]) -> str:
    return _hash_jcs(PARAMETERS_DOMAIN_V1, parameters, allow_floats=True)


def hash_intent_v1(intent: str) -> str:
    if not intent:
        raise ValueError("intent must not be empty")
    return _hash_jcs(INTENT_DOMAIN_V1, intent, allow_floats=False)


def assert_canonical_delegation_id(value: str) -> str:
    if not _DELEGATION_ID.fullmatch(value) or int(value) > _MAX_SAFE_INTEGER:
        raise ValueError("delegation_id must be a canonical positive safe integer string")
    return value


def _assert_sha256(value: str, field: str) -> None:
    if not _SHA256_HEX.fullmatch(value):
        raise ValueError(f"{field} must be lowercase SHA-256 hex")


def build_action_context_preimage_v1(
    request: AuthorityEvaluationRequest,
    *,
    environment: Optional[str] = None,
    agent_version: Optional[str] = None,
) -> Dict[str, Any]:
    action = request.action
    if not action.tool:
        raise ValueError("tool must not be empty")
    _assert_sha256(action.parameters_hash, "parameters_hash")
    preimage: Dict[str, Any] = {
        "action_context_version": ACTION_CONTEXT_VERSION_V1,
        "tool": action.tool,
        "parameters_hash": action.parameters_hash,
        "agent_id": request.agent_id,
        "controller_id": request.controller_id,
    }
    if action.target is not None:
        preimage["target"] = action.target
    if action.intent_hash is not None:
        _assert_sha256(action.intent_hash, "intent_hash")
        preimage["intent_hash"] = action.intent_hash
    if environment is not None:
        preimage["environment"] = environment
    if agent_version is not None:
        preimage["agent_version"] = agent_version
    if action.amount_minor is not None:
        preimage["amount_minor"] = action.amount_minor
    if action.currency is not None:
        preimage["currency"] = action.currency
    preimage["delegation_id"] = assert_canonical_delegation_id(request.delegation_id)
    return preimage


def compute_action_context_hash_v1(
    request: AuthorityEvaluationRequest,
    *,
    environment: Optional[str] = None,
    agent_version: Optional[str] = None,
) -> str:
    return _hash_jcs(
        ACTION_CONTEXT_DOMAIN_V1,
        build_action_context_preimage_v1(
            request, environment=environment, agent_version=agent_version
        ),
        allow_floats=False,
    )
