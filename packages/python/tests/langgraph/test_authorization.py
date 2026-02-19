"""Tests for the Nuggets LangGraph authorization helpers."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from langgraph_sdk.auth.exceptions import HTTPException

from langchain_nuggets.langgraph.authorization import (
    ownership_filter,
    require_kyc,
    require_scopes,
)


def _make_ctx(user: dict) -> MagicMock:
    ctx = MagicMock()
    ctx.user = user
    return ctx


@pytest.mark.asyncio
async def test_require_kyc_blocks_unverified():
    handler = require_kyc()
    ctx = _make_ctx({"identity": "user-1", "kyc_verified": False})

    with pytest.raises(HTTPException) as exc_info:
        await handler(ctx, {})

    assert exc_info.value.status_code == 403
    assert "KYC" in exc_info.value.detail


@pytest.mark.asyncio
async def test_require_kyc_allows_verified():
    handler = require_kyc()
    ctx = _make_ctx({"identity": "user-1", "kyc_verified": True})

    result = await handler(ctx, {"some": "data"})
    assert result == {"some": "data"}


@pytest.mark.asyncio
async def test_require_scopes_blocks_missing():
    handler = require_scopes("email", "profile")
    ctx = _make_ctx({"identity": "user-1", "scopes": ["email"]})

    with pytest.raises(HTTPException) as exc_info:
        await handler(ctx, {})

    assert exc_info.value.status_code == 403
    assert "profile" in exc_info.value.detail


@pytest.mark.asyncio
async def test_require_scopes_allows_matching():
    handler = require_scopes("email", "profile")
    ctx = _make_ctx({"identity": "user-1", "scopes": ["email", "profile", "openid"]})

    result = await handler(ctx, {"some": "data"})
    assert result == {"some": "data"}


@pytest.mark.asyncio
async def test_ownership_filter_sets_owner_on_create():
    handler = ownership_filter()
    ctx = _make_ctx({"identity": "user-42"})
    metadata = {"title": "My Thread"}

    result = await handler(ctx, metadata)

    assert result["owner"] == "user-42"
    assert result["title"] == "My Thread"


@pytest.mark.asyncio
async def test_ownership_filter_returns_filter_on_read():
    handler = ownership_filter()
    ctx = _make_ctx({"identity": "user-42"})

    # For read operations, value is typically None or a non-dict
    result = await handler(ctx, None)

    assert result == {"owner": "user-42"}
