"""Verify age tool."""
from __future__ import annotations

import json
from typing import Optional, Type

from langchain_core.callbacks import CallbackManagerForToolRun, AsyncCallbackManagerForToolRun
from pydantic import BaseModel, Field

from langchain_nuggets.tools.base import NuggetsBaseTool


class VerifyAgeInput(BaseModel):
    userId: str = Field(description="The user's identifier (email or Nuggets address)")
    minimumAge: int = Field(description="The minimum age to verify (e.g. 18 for age-restricted content)")


class VerifyAge(NuggetsBaseTool):
    name: str = "verify_age"
    description: str = "Request selective disclosure age verification for a user. Proves the user meets a minimum age requirement WITHOUT revealing their actual date of birth. Returns a deeplink/QR code for the user to approve the age proof in their Nuggets app. Use check_kyc_status with the returned sessionId to check if the user approved."
    args_schema: Type[BaseModel] = VerifyAgeInput

    def _run(self, userId: str, minimumAge: int, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        result = self.client.post("/kyc/verify-age", {"userId": userId, "minimumAge": minimumAge})
        return json.dumps(result)

    async def _arun(self, userId: str, minimumAge: int, run_manager: Optional[AsyncCallbackManagerForToolRun] = None) -> str:
        result = await self.client.apost("/kyc/verify-age", {"userId": userId, "minimumAge": minimumAge})
        return json.dumps(result)
