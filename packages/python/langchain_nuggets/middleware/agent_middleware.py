"""AgentMiddleware adapter for use with ``langchain.agents.create_agent``.

The core :class:`NuggetsAuthorityMiddleware` only depends on ``langchain-core``
and is driven through ``ToolNode(wrap_tool_call=...)``. LangChain's first-class
``create_agent(middleware=[...])`` API instead expects an ``AgentMiddleware``
subclass, which lives in ``langchain`` (>=1.0).

This module provides that subclass. It composes the core middleware so the full
verified enforcement path (bearer, agent_proof, discover-and-pin proof
verification, fail-closed) is reused unchanged. Importing this module requires
``langchain``::

    pip install langchain-nuggets[agent]
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware  # requires langchain>=1.0

from langchain_nuggets.middleware.authority_middleware import NuggetsAuthorityMiddleware
from langchain_nuggets.middleware.types import MiddlewareConfig, ProofArtifact


class NuggetsAuthorityAgentMiddleware(AgentMiddleware):
    """Nuggets Authority enforcement as a LangChain ``AgentMiddleware``.

    Usage with ``create_agent``::

        from langchain.agents import create_agent
        from langchain_nuggets.middleware.agent_middleware import (
            NuggetsAuthorityAgentMiddleware,
        )

        middleware = NuggetsAuthorityAgentMiddleware(config)
        agent = create_agent(model=..., tools=[...], middleware=[middleware])

    Every tool call is evaluated against the Nuggets authority endpoint before
    execution; DENY/ERROR fail closed and ALLOW emits a signed proof artifact.
    """

    def __init__(self, config: MiddlewareConfig) -> None:
        super().__init__()
        self._mw = NuggetsAuthorityMiddleware(config)

    @property
    def proofs(self) -> list[ProofArtifact]:
        """All proof artifacts emitted during this middleware's lifetime."""
        return self._mw.proofs

    def wrap_tool_call(
        self, request: Any, handler: Callable[[Any], Any]
    ) -> Any:
        return self._mw.wrap_tool_call(request, handler)

    async def awrap_tool_call(
        self, request: Any, handler: Callable[[Any], Awaitable[Any]]
    ) -> Any:
        return await self._mw.awrap_tool_call(request, handler)
