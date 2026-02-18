import json
from typing import Optional, Type

from langchain_core.callbacks import CallbackManagerForToolRun
from pydantic import BaseModel, Field

from langchain_nuggets.client.nuggets_api_client import NuggetsApiClient
from langchain_nuggets.tools.base import NuggetsBaseTool

TEST_CONFIG = {
    "api_url": "https://api.nuggets.test",
    "partner_id": "test-partner",
    "partner_secret": "test-secret",
}


class TestInput(BaseModel):
    input_text: str = Field(description="Test input")


class TestTool(NuggetsBaseTool):
    name: str = "test_tool"
    description: str = "A test tool"
    args_schema: Type[BaseModel] = TestInput

    def _run(
        self, input_text: str, run_manager: Optional[CallbackManagerForToolRun] = None
    ) -> str:
        return f"processed: {input_text}"


class TestNuggetsBaseTool:
    def test_create_with_client(self):
        client = NuggetsApiClient(TEST_CONFIG)
        tool = TestTool(client=client)
        assert tool.name == "test_tool"

    def test_invoke(self):
        client = NuggetsApiClient(TEST_CONFIG)
        tool = TestTool(client=client)
        result = tool.invoke({"input_text": "hello"})
        assert result == "processed: hello"
