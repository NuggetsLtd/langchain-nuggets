"""Initiate OAuth flow tool."""
from __future__ import annotations

import json
from typing import List, Optional, Type

from langchain_core.callbacks import CallbackManagerForToolRun, AsyncCallbackManagerForToolRun
from pydantic import BaseModel, Field

from langchain_nuggets.tools.base import NuggetsBaseTool


class InitiateOAuthFlowInput(BaseModel):
    redirectUri: str = Field(description="The URL to redirect the user to after authentication")
    scopes: Optional[List[str]] = Field(default=None, description='OAuth scopes to request (e.g. ["openid", "profile", "email"]). Defaults to ["openid"]')


class InitiateOAuthFlow(NuggetsBaseTool):
    name: str = "initiate_oauth_flow"
    description: str = "Start an OAuth 2.0 / OpenID Connect authentication flow with Nuggets as the identity provider. Returns an authorization URL that the user should be redirected to. After the user authenticates via Nuggets (QR scan, biometrics, or WebAuthn), they will be redirected back to the redirectUri with an authorization code."
    args_schema: Type[BaseModel] = InitiateOAuthFlowInput

    def _run(self, redirectUri: str, scopes: Optional[List[str]] = None, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        result = self.client.post("/oauth/authorize", {"redirectUri": redirectUri, "scopes": scopes or ["openid"]})
        return json.dumps(result)

    async def _arun(self, redirectUri: str, scopes: Optional[List[str]] = None, run_manager: Optional[AsyncCallbackManagerForToolRun] = None) -> str:
        result = await self.client.apost("/oauth/authorize", {"redirectUri": redirectUri, "scopes": scopes or ["openid"]})
        return json.dumps(result)
