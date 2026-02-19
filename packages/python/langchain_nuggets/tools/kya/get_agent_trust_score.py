"""Get agent trust score tool."""
from __future__ import annotations
from urllib.parse import quote

import json
from typing import Optional, Type

from langchain_core.callbacks import AsyncCallbackManagerForToolRun, CallbackManagerForToolRun
from pydantic import BaseModel, Field

from langchain_nuggets.tools.base import NuggetsBaseTool


class GetAgentTrustScoreInput(BaseModel):
    agentId: str = Field(description="The agent ID or DID to get the trust score for")


class GetAgentTrustScore(NuggetsBaseTool):
    name: str = "get_agent_trust_score"
    description: str = "Get the trust score and provenance signals for an AI agent. Returns a score (0-1) based on verified signals: GitHub account verification, social profile verification, and registration age. Higher scores indicate more trustworthy agents with stronger developer provenance."
    args_schema: Type[BaseModel] = GetAgentTrustScoreInput

    def _run(self, agentId: str, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        result = self.client.get(f"/kya/agents/{quote(agentId, safe="")}/trust-score")
        return json.dumps(result)

    async def _arun(self, agentId: str, run_manager: Optional[AsyncCallbackManagerForToolRun] = None) -> str:
        result = await self.client.aget(f"/kya/agents/{quote(agentId, safe="")}/trust-score")
        return json.dumps(result)
