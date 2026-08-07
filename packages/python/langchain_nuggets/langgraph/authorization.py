"""Pre-built authorization handlers for common Nuggets identity patterns."""
from __future__ import annotations

from typing import Any, Callable, Dict


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

    Implements LangGraph's ownership contract for every operation:

    - **Create/update** (dict ``value``): stamps ``value["metadata"]["owner"]``
      with the caller's identity — where LangGraph persists ownership. (It does
      **not** write a top-level ``value["owner"]``.)
    - **All operations**: returns the exact-match filter ``{"owner": identity}``
      so read/search/update/delete only touch the caller's own resources.

    Fails **closed** (HTTP 403) when there is no authenticated identity — never
    create an unowned resource or an ``owner=None`` filter that could match
    another tenant's data.

    Register it for each operation you want owner-scoped::

        from langchain_nuggets.langgraph import ownership_filter

        for op in (auth.on.threads.create, auth.on.threads.read,
                   auth.on.threads.update, auth.on.threads.delete,
                   auth.on.threads.search):
            op(ownership_filter())
    """

    async def handler(ctx: Any, value: Any) -> Dict[str, str]:
        user = ctx.user if hasattr(ctx, "user") else ctx
        identity = _get_user_field(user, "identity")

        if not identity:
            from langgraph_sdk.auth.exceptions import HTTPException

            raise HTTPException(
                status_code=403,
                detail="Ownership enforcement requires an authenticated identity.",
            )

        # Create/update payloads: stamp ownership where LangGraph stores it.
        if isinstance(value, dict):
            metadata = value.setdefault("metadata", {})
            if isinstance(metadata, dict):
                metadata["owner"] = identity

        # Every operation is scoped to the caller's own resources.
        return {"owner": identity}

    return handler


def _get_user_field(user: Any, field: str) -> Any:
    """Extract a field from a user object (dict or object with attributes)."""
    if isinstance(user, dict):
        return user.get(field)
    return getattr(user, field, None)
