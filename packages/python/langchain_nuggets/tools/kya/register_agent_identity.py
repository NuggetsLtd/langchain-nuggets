"""Register agent identity tool."""
from __future__ import annotations

import json
from typing import Optional, Type

from langchain_core.callbacks import CallbackManagerForToolRun, AsyncCallbackManagerForToolRun
from pydantic import BaseModel, Field

from langchain_nuggets.tools.base import NuggetsBaseTool


class RegisterAgentIdentityInput(BaseModel):
    agentName: str = Field(description="A human-readable name for this AI agent")
    githubUrl: Optional[str] = Field(default=None, description="GitHub profile or repo URL for developer provenance verification")
    twitterHandle: Optional[str] = Field(default=None, description="Twitter/X handle for social verification")


class RegisterAgentIdentity(NuggetsBaseTool):
    name: str = "register_agent_identity"
    description: str = "Register this AI agent's identity with Nuggets to establish verifiable provenance. Provide developer provenance signals (GitHub, Twitter) so other agents and users can verify who built this agent. Returns a DID and agent identity record."
    args_schema: Type[BaseModel] = RegisterAgentIdentityInput

    def _run(self, agentName: str, githubUrl: Optional[str] = None, twitterHandle: Optional[str] = None, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        body: dict = {"agentName": agentName}
        if githubUrl is not None:
            body["githubUrl"] = githubUrl
        if twitterHandle is not None:
            body["twitterHandle"] = twitterHandle
        result = self.client.post("/kya/agents", body)
        return json.dumps(result)

    async def _arun(self, agentName: str, githubUrl: Optional[str] = None, twitterHandle: Optional[str] = None, run_manager: Optional[AsyncCallbackManagerForToolRun] = None) -> str:
        body: dict = {"agentName": agentName}
        if githubUrl is not None:
            body["githubUrl"] = githubUrl
        if twitterHandle is not None:
            body["twitterHandle"] = twitterHandle
        result = await self.client.apost("/kya/agents", body)
        return json.dumps(result)
