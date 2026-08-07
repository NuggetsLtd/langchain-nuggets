"""Tests for the Nuggets LangGraph authorization helpers."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from langgraph_sdk.auth.exceptions import HTTPException

from langchain_nuggets.langgraph.authorization import ownership_filter, require_scopes


def _make_ctx(user: dict) -> MagicMock:
    ctx = MagicMock()
    ctx.user = user
    return ctx


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
async def test_ownership_filter_stamps_metadata_owner_on_create():
    # LangGraph persists ownership under value["metadata"]["owner"], NOT top-level.
    handler = ownership_filter()
    ctx = _make_ctx({"identity": "user-42"})
    value = {"title": "My Thread"}

    result = await handler(ctx, value)

    assert value["metadata"]["owner"] == "user-42"
    assert value["title"] == "My Thread"
    assert "owner" not in value  # not stamped at the top level
    assert result == {"owner": "user-42"}  # and an owner filter is returned


@pytest.mark.asyncio
async def test_ownership_filter_preserves_existing_metadata():
    handler = ownership_filter()
    ctx = _make_ctx({"identity": "user-42"})
    value = {"metadata": {"title": "keep me"}}

    await handler(ctx, value)

    assert value["metadata"]["owner"] == "user-42"
    assert value["metadata"]["title"] == "keep me"


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, {}, {"query": "x"}])
async def test_ownership_filter_returns_owner_filter_for_all_ops(value):
    # read/search/update/delete (value may be None OR a dict) must return the
    # exact-match owner filter — a dict value must not be misrouted.
    handler = ownership_filter()
    ctx = _make_ctx({"identity": "user-42"})

    result = await handler(ctx, value)

    assert result == {"owner": "user-42"}


@pytest.mark.asyncio
async def test_ownership_filter_fails_closed_without_identity():
    # No identity → never create an unowned resource or an owner=None filter.
    handler = ownership_filter()
    ctx = _make_ctx({"identity": None})

    with pytest.raises(HTTPException) as exc_info:
        await handler(ctx, {"title": "x"})

    assert exc_info.value.status_code == 403
