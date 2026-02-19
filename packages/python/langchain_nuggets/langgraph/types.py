"""Type definitions for the Nuggets LangGraph auth integration."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class NuggetsAuthConfig(BaseModel):
    """Configuration for the Nuggets LangGraph auth provider."""

    issuer_url: str
    api_url: Optional[str] = None
    partner_id: Optional[str] = None
    partner_secret: Optional[str] = None
    audience: Optional[str] = None
    jwks_cache_ttl: int = 3600
    require_kyc: bool = False


class NuggetsUserInfo(BaseModel):
    """User information extracted from a verified Nuggets OIDC token."""

    sub: str
    email: Optional[str] = None
    name: Optional[str] = None
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    kyc_verified: bool = False
    scopes: List[str] = []
    raw_claims: Dict[str, Any] = {}
