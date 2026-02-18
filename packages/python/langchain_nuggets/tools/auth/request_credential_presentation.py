"""Request credential presentation tool."""
from __future__ import annotations

import json
from typing import List, Optional, Type

from langchain_core.callbacks import CallbackManagerForToolRun, AsyncCallbackManagerForToolRun
from pydantic import BaseModel, Field

from langchain_nuggets.tools.base import NuggetsBaseTool


class RequestCredentialPresentationInput(BaseModel):
    userId: str = Field(description="The user's identifier (email or Nuggets address)")
    credentialTypes: List[str] = Field(description='Array of credential types to request (e.g. ["email", "phone", "address"])')


class RequestCredentialPresentation(NuggetsBaseTool):
    name: str = "request_credential_presentation"
    description: str = "Ask a user to present one or more verifiable credentials from their Nuggets app. Specify which credential types you need. The user will see a request in their app and can approve or reject sharing each credential. Use verify_presentation with the returned sessionId to check if the user responded."
    args_schema: Type[BaseModel] = RequestCredentialPresentationInput

    def _run(self, userId: str, credentialTypes: List[str], run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        result = self.client.post("/credentials/presentations", {"userId": userId, "credentialTypes": credentialTypes})
        return json.dumps(result)

    async def _arun(self, userId: str, credentialTypes: List[str], run_manager: Optional[AsyncCallbackManagerForToolRun] = None) -> str:
        result = await self.client.apost("/credentials/presentations", {"userId": userId, "credentialTypes": credentialTypes})
        return json.dumps(result)
