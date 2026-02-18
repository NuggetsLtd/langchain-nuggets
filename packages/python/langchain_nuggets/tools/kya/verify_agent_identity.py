"""Verify agent identity tool."""
from __future__ import annotations

import json
from typing import Optional, Type

from langchain_core.callbacks import CallbackManagerForToolRun, AsyncCallbackManagerForToolRun
from pydantic import BaseModel, Field

from langchain_nuggets.tools.base import NuggetsBaseTool


class VerifyAgentIdentityInput(BaseModel):
    agentId: str = Field(description="The agent ID or DID of the agent to verify")


class VerifyAgentIdentity(NuggetsBaseTool):
    name: str = "verify_agent_identity"
    description: str = "Verify another AI agent's identity through Nuggets. Returns the agent's registered identity including DID, developer provenance signals, and registration date. Use this before trusting data from or sharing data with another agent."
    args_schema: Type[BaseModel] = VerifyAgentIdentityInput

    def _run(self, agentId: str, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        result = self.client.get(f"/kya/agents/{agentId}")
        return json.dumps(result)

    async def _arun(self, agentId: str, run_manager: Optional[AsyncCallbackManagerForToolRun] = None) -> str:
        result = await self.client.aget(f"/kya/agents/{agentId}")
        return json.dumps(result)
