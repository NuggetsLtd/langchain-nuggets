"""NuggetsAuthorityMiddleware — tool-call interception for trust enforcement."""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from langchain_core.messages import ToolMessage

from langchain_nuggets.client.nuggets_api_client import NuggetsApiClient
from langchain_nuggets.middleware.proof import (
    build_proof_artifact,
    hash_parameters,
    hash_result,
)
from langchain_nuggets.middleware.types import (
    ActionContext,
    AuthorityEvaluationRequest,
    AuthorityEvaluationResponse,
    MiddlewareConfig,
    ProofArtifact,
)

logger = logging.getLogger(__name__)


class NuggetsAuthorityMiddleware:
    """Middleware that intercepts LangChain/LangGraph tool calls and enforces
    Nuggets trust primitives: Actor Identity, Authority, Policy, Intent,
    Consent, and Accountability.

    Provides wrap_tool_call and awrap_tool_call functions compatible with
    LangGraph's ToolNode and create_react_agent.

    Usage with ToolNode::

        middleware = NuggetsAuthorityMiddleware(config)
        tool_node = ToolNode(
            tools=tools,
            wrap_tool_call=middleware.wrap_tool_call,
        )
    """

    def __init__(self, config: MiddlewareConfig) -> None:
        self._config = config
        self._client = NuggetsApiClient(
            {
                "api_url": config.api_url,
                "partner_id": config.partner_id,
                "partner_secret": config.partner_secret,
                "ca_cert": config.ca_cert,
                "verify_ssl": config.verify_ssl,
            }
        )
        self._proofs: List[ProofArtifact] = []
        self._on_proof: Optional[Callable[[ProofArtifact], Any]] = config.on_proof

    @property
    def proofs(self) -> List[ProofArtifact]:
        """All proof artifacts emitted during this middleware's lifetime."""
        return list(self._proofs)

    def _build_eval_request(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
    ) -> AuthorityEvaluationRequest:
        """Construct the authority evaluation request payload."""
        # Resolve intent via callback if configured
        intent = None
        if self._config.intent_resolver is not None:
            intent = self._config.intent_resolver(tool_name, tool_args)

        # Extract target from args if present, otherwise default to tool name
        target = tool_args.get("target", tool_name) if isinstance(tool_args, dict) else tool_name

        return AuthorityEvaluationRequest(
            agent_id=self._config.agent_id,
            controller_id=self._config.controller_id,
            delegation_id=self._config.delegation_id,
            action=ActionContext(
                tool=tool_name,
                target=str(target),
                parameters_hash=hash_parameters(tool_args),
                intent=intent,
                timestamp=datetime.now(timezone.utc).isoformat(),
            ),
        )

    def _make_deny_message(
        self,
        tool_call_id: str,
        tool_name: str,
        response: AuthorityEvaluationResponse,
    ) -> ToolMessage:
        """Create a structured ToolMessage for a DENY decision."""
        content = json.dumps(
            {
                "status": "DENIED",
                "tool": tool_name,
                "reason_code": response.reason_code,
                "proof_id": response.proof_id,
                "message": f"Authority check denied execution of '{tool_name}'"
                + (f": {response.reason_code}" if response.reason_code else ""),
            }
        )
        return ToolMessage(content=content, tool_call_id=tool_call_id)

    def _emit_proof(self, proof: ProofArtifact) -> None:
        """Store proof and invoke callback if configured."""
        self._proofs.append(proof)
        if self._on_proof is not None:
            self._on_proof(proof)

    def wrap_tool_call(self, request: Any, handler: Any) -> Any:
        """Synchronous tool call wrapper compatible with LangGraph ToolNode.

        Evaluates authority before tool execution. On ALLOW, executes the tool
        and emits a proof artifact. On DENY, returns a structured error ToolMessage.
        """
        tool_call = request.tool_call
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        tool_call_id = tool_call["id"]

        eval_request = self._build_eval_request(tool_name, tool_args)
        start_time = time.monotonic()

        try:
            raw_response = self._client.post(
                self._config.authority_endpoint,
                eval_request.model_dump(),
            )
            auth_response = AuthorityEvaluationResponse(**raw_response)
        except Exception as exc:
            logger.error("Authority evaluation failed: %s", exc)
            return ToolMessage(
                content=json.dumps(
                    {
                        "status": "ERROR",
                        "tool": tool_name,
                        "message": f"Authority evaluation failed: {exc}",
                    }
                ),
                tool_call_id=tool_call_id,
            )

        if auth_response.decision == "DENY":
            logger.info("DENY: tool=%s reason=%s", tool_name, auth_response.reason_code)
            return self._make_deny_message(tool_call_id, tool_name, auth_response)

        logger.info("ALLOW: tool=%s proof_id=%s", tool_name, auth_response.proof_id)
        result = handler(request)

        result_content = ""
        if isinstance(result, ToolMessage):
            result_content = (
                result.content if isinstance(result.content, str) else str(result.content)
            )

        total_latency = (time.monotonic() - start_time) * 1000
        proof = build_proof_artifact(
            authority_response=auth_response,
            agent_id=self._config.agent_id,
            controller_id=self._config.controller_id,
            delegation_id=self._config.delegation_id,
            tool=tool_name,
            parameters_hash=hash_parameters(tool_args),
            result_hash=hash_result(result_content),
            latency_ms=total_latency,
        )
        self._emit_proof(proof)

        return result

    async def awrap_tool_call(self, request: Any, handler: Any) -> Any:
        """Asynchronous tool call wrapper compatible with LangGraph ToolNode.

        Async variant of wrap_tool_call. Uses the async NuggetsApiClient methods.
        """
        tool_call = request.tool_call
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        tool_call_id = tool_call["id"]

        eval_request = self._build_eval_request(tool_name, tool_args)
        start_time = time.monotonic()

        try:
            raw_response = await self._client.apost(
                self._config.authority_endpoint,
                eval_request.model_dump(),
            )
            auth_response = AuthorityEvaluationResponse(**raw_response)
        except Exception as exc:
            logger.error("Authority evaluation failed: %s", exc)
            return ToolMessage(
                content=json.dumps(
                    {
                        "status": "ERROR",
                        "tool": tool_name,
                        "message": f"Authority evaluation failed: {exc}",
                    }
                ),
                tool_call_id=tool_call_id,
            )

        if auth_response.decision == "DENY":
            logger.info("DENY: tool=%s reason=%s", tool_name, auth_response.reason_code)
            return self._make_deny_message(tool_call_id, tool_name, auth_response)

        logger.info("ALLOW: tool=%s proof_id=%s", tool_name, auth_response.proof_id)
        result = await handler(request)

        result_content = ""
        if isinstance(result, ToolMessage):
            result_content = (
                result.content if isinstance(result.content, str) else str(result.content)
            )

        total_latency = (time.monotonic() - start_time) * 1000
        proof = build_proof_artifact(
            authority_response=auth_response,
            agent_id=self._config.agent_id,
            controller_id=self._config.controller_id,
            delegation_id=self._config.delegation_id,
            tool=tool_name,
            parameters_hash=hash_parameters(tool_args),
            result_hash=hash_result(result_content),
            latency_ms=total_latency,
        )
        self._emit_proof(proof)

        return result
