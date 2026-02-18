"""Initiate KYC verification tool."""
from __future__ import annotations

import json
from typing import Optional, Type

from langchain_core.callbacks import CallbackManagerForToolRun, AsyncCallbackManagerForToolRun
from pydantic import BaseModel, Field

from langchain_nuggets.tools.base import NuggetsBaseTool


class InitiateKycVerificationInput(BaseModel):
    userId: str = Field(description="The user's identifier (email or Nuggets address) to start KYC verification for")


class InitiateKycVerification(NuggetsBaseTool):
    name: str = "initiate_kyc_verification"
    description: str = "Start a KYC (Know Your Customer) identity verification flow for a user. Returns a deeplink and QR code URL that the user must scan with their Nuggets app to complete identity verification. Use check_kyc_status to poll for completion."
    args_schema: Type[BaseModel] = InitiateKycVerificationInput

    def _run(self, userId: str, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        result = self.client.post("/kyc/sessions", {"userId": userId})
        return json.dumps(result)

    async def _arun(self, userId: str, run_manager: Optional[AsyncCallbackManagerForToolRun] = None) -> str:
        result = await self.client.apost("/kyc/sessions", {"userId": userId})
        return json.dumps(result)
