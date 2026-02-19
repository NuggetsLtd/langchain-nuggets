"""Pre-built authorization handlers for common Nuggets identity patterns."""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Sequence


def require_kyc() -> Callable:
    """Create an authorization handler that requires KYC verification.

    Rejects any request where the authenticated user does not have
    ``kyc_verified=True`` in their user dict (set by NuggetsAuth during
    authentication when the user's KYC status is confirmed).

    Usage::

        from langchain_nuggets.langgraph import require_kyc

        @auth.on.threads.create
        async def on_create(ctx, value):
            return await require_kyc()(ctx, value)
    """

    async def handler(ctx: Any, value: Any) -> Any:
        user = ctx.user if hasattr(ctx, "user") else ctx
        if not _get_user_field(user, "kyc_verified"):
            from langgraph_sdk.auth.exceptions import HTTPException

            raise HTTPException(
                status_code=403,
                detail="KYC verification required for this operation",
            )
        return value

    return handler


def require_scopes(*scopes: str) -> Callable:
    """Create an authorization handler that requires specific OIDC scopes.

    Rejects any request where the authenticated user is missing one or more
    of the required scopes.

    Args:
        *scopes: One or more scope strings that must all be present.

    Usage::

        from langchain_nuggets.langgraph import require_scopes

        @auth.on.threads.create
        async def on_create(ctx, value):
            return await require_scopes("email", "profile")(ctx, value)
    """

    async def handler(ctx: Any, value: Any) -> Any:
        user = ctx.user if hasattr(ctx, "user") else ctx
        user_scopes = set(_get_user_field(user, "scopes") or [])
        missing = set(scopes) - user_scopes
        if missing:
            from langgraph_sdk.auth.exceptions import HTTPException

            raise HTTPException(
                status_code=403,
                detail=f"Missing required scopes: {', '.join(sorted(missing))}",
            )
        return value

    return handler


def ownership_filter() -> Callable:
    """Create an authorization handler that enforces resource ownership.

    On **create** actions, sets ``metadata["owner"]`` to the user's identity.
    On **read/search** actions, returns a filter dict so only resources owned
    by the current user are returned.

    Usage::

        from langchain_nuggets.langgraph import ownership_filter

        @auth.on.threads.create
        async def on_create(ctx, value):
            return await ownership_filter()(ctx, value)

        @auth.on.threads.read
        async def on_read(ctx, value):
            return await ownership_filter()(ctx, value)
    """

    async def handler(ctx: Any, value: Any) -> Any:
        user = ctx.user if hasattr(ctx, "user") else ctx
        identity = _get_user_field(user, "identity")

        # If value is a dict (typical for create metadata), add owner
        if isinstance(value, dict):
            value["owner"] = identity
            return value

        # For read/search, return a filter
        return {"owner": identity}

    return handler


def _get_user_field(user: Any, field: str) -> Any:
    """Extract a field from a user object (dict or object with attributes)."""
    if isinstance(user, dict):
        return user.get(field)
    return getattr(user, field, None)
