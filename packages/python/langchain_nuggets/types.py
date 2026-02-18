"""Type definitions for the Nuggets LangChain toolkit."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel


class WebhookConfig(BaseModel):
    callback_url: str
    secret: str


class NuggetsConfig(BaseModel):
    api_url: str
    partner_id: str
    partner_secret: str
    webhook: Optional[WebhookConfig] = None


class KycSession(BaseModel):
    session_id: str
    deeplink: str
    qr_code_url: str


KycStatus = Literal["pending", "completed", "failed", "expired"]


class VerifiableCredential(BaseModel):
    id: str
    type: List[str]
    issuer: str
    issuance_date: str
    credential_subject: Dict[str, Any]
    proof: Optional[Dict[str, Any]] = None


class KycResult(BaseModel):
    session_id: str
    status: KycStatus
    credentials: Optional[List[VerifiableCredential]] = None


class AgentProvenance(BaseModel):
    github: Optional[str] = None
    twitter: Optional[str] = None


class AgentIdentity(BaseModel):
    agent_id: str
    did: str
    provenance: AgentProvenance
    registered_at: str


class TrustSignals(BaseModel):
    github_verified: bool
    social_verified: bool
    registration_age: int


class AgentTrustScore(BaseModel):
    agent_id: str
    score: float
    signals: TrustSignals


class CredentialPresentation(BaseModel):
    session_id: str
    deeplink: str
    qr_code_url: str


PresentationStatus = Literal["pending", "presented", "rejected", "expired"]


class PresentationResult(BaseModel):
    session_id: str
    status: PresentationStatus
    credentials: Optional[List[VerifiableCredential]] = None
    verified: Optional[bool] = None


class OAuthSession(BaseModel):
    authorization_url: str
    state: str
    code_verifier: str


class OAuthTokenResult(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    id_token: Optional[str] = None
    expires_in: int
    token_type: str


class AuthStatus(BaseModel):
    authenticated: bool
    user_id: Optional[str] = None
    kyc_verified: Optional[bool] = None
    credentials: Optional[List[str]] = None
