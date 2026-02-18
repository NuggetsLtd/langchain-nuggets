"""Check auth status tool."""
from __future__ import annotations

import json
from typing import Optional, Type

from langchain_core.callbacks import AsyncCallbackManagerForToolRun, CallbackManagerForToolRun
from pydantic import BaseModel, Field

from langchain_nuggets.tools.base import NuggetsBaseTool


class CheckAuthStatusInput(BaseModel):
    userId: str = Field(description="The user's identifier to check authentication status for")


class CheckAuthStatus(NuggetsBaseTool):
    name: str = "check_auth_status"
    description: str = "Check whether a user is currently authenticated with Nuggets and their verification status. Returns whether the user is authenticated, their KYC verification status, and which credentials they have on file. Use this to gate access to sensitive operations that require verified identity."
    args_schema: Type[BaseModel] = CheckAuthStatusInput

    def _run(self, userId: str, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        result = self.client.get(f"/auth/status/{userId}")
        return json.dumps(result)

    async def _arun(self, userId: str, run_manager: Optional[AsyncCallbackManagerForToolRun] = None) -> str:
        result = await self.client.aget(f"/auth/status/{userId}")
        return json.dumps(result)
