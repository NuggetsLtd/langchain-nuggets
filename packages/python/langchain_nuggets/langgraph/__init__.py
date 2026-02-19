"""LangGraph auth integration with Nuggets identity provider.

Requires the ``langgraph`` extra::

    pip install langchain-nuggets[langgraph]
"""
from langchain_nuggets.langgraph.auth import NuggetsAuth
from langchain_nuggets.langgraph.authorization import (
    ownership_filter,
    require_kyc,
    require_scopes,
)
from langchain_nuggets.langgraph.token_verifier import NuggetsAuthError, NuggetsTokenVerifier
from langchain_nuggets.langgraph.types import NuggetsAuthConfig, NuggetsUserInfo

__all__ = [
    "NuggetsAuth",
    "NuggetsAuthConfig",
    "NuggetsAuthError",
    "NuggetsTokenVerifier",
    "NuggetsUserInfo",
    "ownership_filter",
    "require_kyc",
    "require_scopes",
]
