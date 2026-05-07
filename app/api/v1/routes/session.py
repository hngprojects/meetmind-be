"""Session lifecycle endpoints: token refresh and logout."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import CurrentUser, DBSession
from app.core.config import settings
from app.models.user import User
from app.schemas.auth import AccessTokenData, LogoutRequest, RefreshRequest, UserData
from app.schemas.response import APIResponse
from app.services.auth import AuthService

router = APIRouter()


def _next_step(user: User) -> str:
    """Derive the frontend routing hint from account state.

    Args:
        user: The authenticated user instance.

    Returns:
        ``"verify_email"`` if the account email is unconfirmed.
        ``"onboarding"`` if the profile is incomplete.
        ``"dashboard"`` if the account is fully set up.
    """
    if not user.is_verified:
        return "verify_email"
    if not user.name or not user.job_title:
        return "onboarding"
    return "dashboard"


@router.post("/refresh", summary="Rotate access token")
async def refresh_token(
    body: RefreshRequest,
    db: DBSession,
) -> APIResponse:
    """Issue a new access token using a valid refresh token.

    The session row's ``last_seen_at`` is updated on every successful call.
    If the refresh token has already been used or the session was deleted
    on logout, a 401 is returned. If a valid-signature token arrives for a
    session that no longer exists, all sessions for that user are wiped
    (theft detection) and a 401 is returned.

    The refresh token itself is NOT rotated — only the access token is
    reissued. This keeps the client flow simple.

    Args:
        body: Request body containing the refresh JWT.
        db: Request-scoped async database session.

    Returns:
        200 with a new :class:`~app.schemas.auth.AccessTokenData` payload.

    Raises:
        HTTPException: 401 if the token is invalid, expired, or the session
            no longer exists.
    """
    try:
        session = await AuthService.rotate_session(db, body.refresh_token)
    except Exception:
        raise HTTPException(
            status_code=401,
            detail={
                "status_code": 401,
                "message": "Invalid or expired refresh token",
                "data": None,
            },
        )

    if session is None:
        raise HTTPException(
            status_code=401,
            detail={
                "status_code": 401,
                "message": "Session not found or already revoked",
                "data": None,
            },
        )

    result = await db.execute(select(User).where(User.id == session.user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=401,
            detail={"status_code": 401, "message": "User not found", "data": None},
        )

    access_token = await AuthService.create_access_token(user)

    return APIResponse(
        status_code=200,
        message="Token refreshed successfully",
        data=AccessTokenData(
            access_token=access_token,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        ).model_dump(),
    )


@router.post("/logout", summary="Invalidate the current session")
async def logout(
    body: LogoutRequest,
    db: DBSession,
    current_user: CurrentUser,
) -> APIResponse:
    """Delete the active session row, invalidating the refresh token.

    Requires a valid access token in the ``Authorization`` header AND the
    refresh token in the request body. The access token is validated first
    via :data:`~app.api.deps.CurrentUser`; if it is missing or invalid the
    request is rejected before the session deletion is attempted.

    After logout the frontend should discard both tokens. Any subsequent
    call with the old refresh token will fail because its session row no
    longer exists.

    Args:
        body: Request body containing the refresh JWT to revoke.
        db: Request-scoped async database session.
        current_user: Authenticated user resolved from the Bearer token.

    Returns:
        200 with a null data payload confirming the session was removed.
    """
    await AuthService.revoke_session(db, body.refresh_token)

    return APIResponse(
        status_code=200,
        message="Logged out successfully",
        data=None,
    )


@router.get("/me", summary="Get the current authenticated user")
async def get_me(current_user: CurrentUser) -> APIResponse:
    """Return the profile of the user identified by the access token.

    No additional database query is made beyond what
    :func:`~app.api.deps.get_current_user` already performs. The
    ``next_step`` field allows the frontend to re-route the user if their
    state has changed since the token was issued (e.g. refreshing on a
    deep link before completing onboarding).

    Args:
        current_user: Authenticated user resolved from the Bearer token.

    Returns:
        200 with a :class:`~app.schemas.auth.UserData` payload including
        the ``next_step`` routing hint.
    """
    return APIResponse(
        status_code=200,
        message="User retrieved successfully",
        data=UserData(
            id=str(current_user.id),
            name=current_user.name,
            email=current_user.email,
            role=current_user.role,
            is_verified=current_user.is_verified,
            next_step=_next_step(current_user),
        ).model_dump(),
    )