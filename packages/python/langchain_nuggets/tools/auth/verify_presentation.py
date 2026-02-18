"""Verify presentation tool."""
from __future__ import annotations

import json
from typing import Optional, Type

from langchain_core.callbacks import AsyncCallbackManagerForToolRun, CallbackManagerForToolRun
from pydantic import BaseModel, Field

from langchain_nuggets.tools.base import NuggetsBaseTool


class VerifyPresentationInput(BaseModel):
    sessionId: str = Field(description="The presentation session ID returned by request_credential_presentation")


class VerifyPresentation(NuggetsBaseTool):
    name: str = "verify_presentation"
    description: str = 'Check the status of a credential presentation request and cryptographically verify any presented credentials. Returns status: "pending" (awaiting user), "presented" (user shared credentials), "rejected" (user declined), or "expired". If presented, includes the verified credentials and a verified boolean.'
    args_schema: Type[BaseModel] = VerifyPresentationInput

    def _run(self, sessionId: str, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        result = self.client.get(f"/credentials/presentations/{sessionId}")
        return json.dumps(result)

    async def _arun(self, sessionId: str, run_manager: Optional[AsyncCallbackManagerForToolRun] = None) -> str:
        result = await self.client.aget(f"/credentials/presentations/{sessionId}")
        return json.dumps(result)
