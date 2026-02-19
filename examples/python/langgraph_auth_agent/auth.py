"""Nuggets auth handler for LangGraph Platform deployment.

This module provides the ``auth`` object that LangGraph Platform uses
to authenticate incoming requests via Nuggets OIDC.

Reads configuration from environment variables:
- NUGGETS_OIDC_ISSUER_URL (required)
- NUGGETS_API_URL (optional, for KYC status enrichment)
- NUGGETS_PARTNER_ID (optional)
- NUGGETS_PARTNER_SECRET (optional)
"""
from langchain_nuggets.langgraph import NuggetsAuth

nuggets = NuggetsAuth(require_kyc=True)
auth = nuggets.auth
