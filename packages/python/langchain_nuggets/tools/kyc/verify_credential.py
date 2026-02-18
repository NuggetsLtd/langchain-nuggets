"""Verify credential tool."""
from __future__ import annotations

import json
from typing import Optional, Type

from langchain_core.callbacks import CallbackManagerForToolRun, AsyncCallbackManagerForToolRun
from pydantic import BaseModel, Field

from langchain_nuggets.tools.base import NuggetsBaseTool


class VerifyCredentialInput(BaseModel):
    userId: str = Field(description="The user's identifier (email or Nuggets address)")
    credentialType: str = Field(description='The type of credential to verify (e.g. "address", "nationality", "email", "phone")')


class VerifyCredential(NuggetsBaseTool):
    name: str = "verify_credential"
    description: str = "Request selective disclosure verification of a specific credential for a user. The user will be asked to share only the requested credential type from their Nuggets app. Returns a deeplink/QR code for the user to approve. Use check_kyc_status with the returned sessionId to check completion."
    args_schema: Type[BaseModel] = VerifyCredentialInput

    def _run(self, userId: str, credentialType: str, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        result = self.client.post("/kyc/verify-credential", {"userId": userId, "credentialType": credentialType})
        return json.dumps(result)

    async def _arun(self, userId: str, credentialType: str, run_manager: Optional[AsyncCallbackManagerForToolRun] = None) -> str:
        result = await self.client.apost("/kyc/verify-credential", {"userId": userId, "credentialType": credentialType})
        return json.dumps(result)
