import pytest

from langchain_nuggets.client.nuggets_api_client import NuggetsApiClient

TEST_CONFIG = {
    "api_url": "https://api.nuggets.test",
    "partner_id": "partner-123",
    "partner_secret": "secret-456",
}


@pytest.fixture
def client():
    return NuggetsApiClient(TEST_CONFIG)
