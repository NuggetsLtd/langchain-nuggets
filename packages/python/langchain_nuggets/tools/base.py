"""Base class for all Nuggets LangChain tools."""
from __future__ import annotations

from langchain_core.tools import BaseTool
from pydantic import ConfigDict

from langchain_nuggets.client.nuggets_api_client import NuggetsApiClient


class NuggetsBaseTool(BaseTool):
    """Base tool that holds a reference to the Nuggets API client."""

    client: NuggetsApiClient
    model_config = ConfigDict(arbitrary_types_allowed=True)
