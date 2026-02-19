"""Base class for all Nuggets LangChain tools."""
from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import ConfigDict

from langchain_nuggets.client.nuggets_api_client import NuggetsApiClient, NuggetsApiClientError


class NuggetsBaseTool(BaseTool):
    """Base tool that holds a reference to the Nuggets API client.

    Wraps invoke to catch NuggetsApiClientError and return structured
    JSON error strings instead of crashing the agent loop.
    """

    client: NuggetsApiClient
    model_config = ConfigDict(arbitrary_types_allowed=True)

    def invoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        try:
            return super().invoke(input, config, **kwargs)
        except NuggetsApiClientError as exc:
            return json.dumps(
                {"error": True, "code": exc.code, "message": str(exc), "status_code": exc.status_code}
            )
