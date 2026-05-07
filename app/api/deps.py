"""Reusable FastAPI dependency aliases."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.responses import APIError
from app.db.session import get_session
from app.models.user import User
from app.services.auth import AuthService

# ── DB session ─────────────────────────────────────────────────────────────────

DBSession = Annotated[AsyncSession, Depends(get_session)]
"""Type alias for an injected request-scoped async database session."""

# ── Auth scheme ────────────────────────────────────────────────────────────────

# auto_error=False lets us return custom auth errors consistently
_bearer = HTTPBearer(auto_error=False)

# ── Current user ───────────────────────────────────────────────────────────────


async def get_current_user(
    db: DBSession,
    access_token: str | None = Cookie(default=None),
    bearer_creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> User:
    """Resolve the authenticated user from a JWT access token.

    Accepts tokens from either:
    - httponly cookie (`access_token`)
    - Authorization: Bearer <token> header

    Args:
        db: Request-scoped async database session.
        access_token: JWT from cookie if present.
        bearer_creds: Parsed bearer credentials from Authorization header.

    Returns:
        The authenticated User ORM object.

    Raises:
        APIError: If token is missing, invalid, expired,
            malformed, or user does not exist.
    """
    token = _resolve_token(access_token, bearer_creds)

    try:
        payload = await AuthService.decode_access_token(token)

        if payload.get("type") != "access":
            raise APIError(
                "Invalid or expired token",
                status_code=status.HTTP_401_UNAUTHORIZED,
                code="unauthorized",
            )

        raw_id: str | None = payload.get("sub")
        if not raw_id:
            raise APIError(
                "Invalid token",
                status_code=status.HTTP_401_UNAUTHORIZED,
                code="unauthorized",
            )

        try:
            user_id = uuid.UUID(raw_id)
        except ValueError:
            raise APIError(
                "Invalid token",
                status_code=status.HTTP_401_UNAUTHORIZED,
                code="unauthorized",
            )

    except JWTError:
        raise APIError(
            "Invalid or expired token",
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="unauthorized",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise APIError(
            "User not found",
            status_code=status.HTTP_404_NOT_FOUND,
            code="user_not_found",
        )

    return user


def _resolve_token(
    cookie_token: str | None,
    bearer_creds: HTTPAuthorizationCredentials | None,
) -> str:
    """Extract JWT from cookie or Authorization header.

    Cookie takes priority over Bearer auth.

    Args:
        cookie_token: access_token cookie value.
        bearer_creds: Parsed bearer credentials.

    Returns:
        Raw JWT string.

    Raises:
        APIError: If no authentication token is provided.
    """
    if cookie_token:
        return cookie_token

    if bearer_creds:
        return bearer_creds.credentials

    raise APIError(
        "Not authenticated",
        status_code=status.HTTP_401_UNAUTHORIZED,
        code="unauthorized",
    )


CurrentUser = Annotated[User, Depends(get_current_user)]
"""Type alias for an injected authenticated user."""