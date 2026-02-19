"""Check KYC status tool."""
from __future__ import annotations
from urllib.parse import quote

import json
from typing import Optional, Type

from langchain_core.callbacks import AsyncCallbackManagerForToolRun, CallbackManagerForToolRun
from pydantic import BaseModel, Field

from langchain_nuggets.tools.base import NuggetsBaseTool


class CheckKycStatusInput(BaseModel):
    sessionId: str = Field(description="The KYC session ID returned by initiate_kyc_verification")


class CheckKycStatus(NuggetsBaseTool):
    name: str = "check_kyc_status"
    description: str = 'Check the status of a KYC verification session. Returns status: "pending" (user has not yet completed), "completed" (verified), "failed" (verification failed), or "expired" (session timed out). If completed, includes the verified credentials.'
    args_schema: Type[BaseModel] = CheckKycStatusInput

    def _run(self, sessionId: str, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        result = self.client.get(f"/kyc/sessions/{quote(sessionId, safe="")}")
        return json.dumps(result)

    async def _arun(self, sessionId: str, run_manager: Optional[AsyncCallbackManagerForToolRun] = None) -> str:
        result = await self.client.aget(f"/kyc/sessions/{quote(sessionId, safe="")}")
        return json.dumps(result)
