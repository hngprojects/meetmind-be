"""Reusable FastAPI dependency aliases."""

from __future__ import annotations
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.user import User
from app.services.auth import AuthService

# ── DB session ─────────────────────────────────────────────────────────────────

DBSession = Annotated[AsyncSession, Depends(get_session)]
"""Type alias for an injected request-scoped async database session."""

# ── Auth scheme ────────────────────────────────────────────────────────────────

bearer_scheme = HTTPBearer()
"""HTTP Bearer token extractor used by :func:`get_current_user`."""

# ── Current user ───────────────────────────────────────────────────────────────

async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    db: DBSession,
) -> User:
    """Decode the Bearer access token and return the matching user.

    Validates the token signature, expiry, and type claim before hitting
    the database. Returns the full :class:`~app.models.user.User` ORM
    object so route handlers receive a ready-to-use instance.

    Args:
        credentials: Bearer token extracted from the Authorization header
            by :data:`bearer_scheme`.
        db: Request-scoped async database session.

    Returns:
        The authenticated :class:`~app.models.user.User` instance.

    Raises:
        HTTPException: 401 for any of the following — missing or malformed
            token, invalid signature, expired token, wrong token type,
            or no matching user in the database. The response never reveals
            which specific check failed.
    """
    credentials_error = HTTPException(
        status_code=401,
        detail={
            "status_code": 401,
            "message": "Invalid or expired token",
            "data": None,
        },
    )

    try:
        payload = await AuthService.decode_access_token(credentials.credentials)

        if payload.get("type") != "access":
            raise credentials_error

        user_id: str | None = payload.get("sub")
        if not user_id:
            raise credentials_error

    except JWTError:
        raise credentials_error

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_error

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
"""Type alias for an injected authenticated user, resolved via Bearer token."""