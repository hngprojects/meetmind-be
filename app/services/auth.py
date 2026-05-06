"""
Forgot password business logic.

Security contract:
    * The endpoint always returns the same response shape regardless of
      whether the email exists.
    * Raw reset tokens are never stored in the database.
    * Tokens expire after a configurable duration.
    * Email delivery failures are logged but never exposed to clients.
"""

import hashlib
import logging
import secrets
import resend
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import PasswordResetToken, User

logger = logging.getLogger(__name__)


def _hash_token(raw_token: str) -> str:
    """
    Hash a raw reset token using SHA-256.

    Args:
        raw_token: Plain-text reset token.

    Returns:
        str: SHA-256 hashed token.
    """
    return hashlib.sha256(raw_token.encode()).hexdigest()


def _build_reset_link(raw_token: str) -> str:
    """
    Build the password reset URL sent to the user.

    Args:
        raw_token: Plain-text password reset token.

    Returns:
        str: Frontend password reset URL.
    """
    return f"{settings.FRONTEND_URL}/reset-password?token={raw_token}"


async def _get_user_by_email(db: AsyncSession, email: str) -> User | None:
    """
    Retrieve a user by email address.

    Args:
        db: Active database session.
        email: User email address.

    Returns:
        User | None: Matching user if found, otherwise None.
    """
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def _create_reset_token(db: AsyncSession, user: User) -> str:
    """
    Create and persist a password reset token.

    The raw token is returned temporarily for email delivery while
    only the hashed version is stored in the database.

    Args:
        db: Active database session.
        user: User requesting password reset.

    Returns:
        str: Raw password reset token.
    """
    raw_token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(
        minutes=settings.RESET_TOKEN_EXPIRE_MINUTES
    )
 
    db_token = PasswordResetToken(
        user_id=user.id,
        token_hash=_hash_token(raw_token),
        expires_at=expires_at,
    )
    db.add(db_token)
    await db.commit()
 
    return raw_token


async def _send_reset_email(email: str, reset_link: str) -> None:
    """
    Send a password reset email.

    Args:
        email: Recipient email address.
        reset_link: Password reset URL.

    Returns:
        None
    """
    resend.api_key = settings.RESEND_API_KEY

    resend.Emails.send({
        "from": "MeetMind <onbording@resend.dev>",
        "to": email,
        "subject": "Reset your MeetMind password",
        "html": (
            f"<p>You requested a password reset.</p>"
            f"<p><a href='{reset_link}'>Click here to reset your password</a></p>"
            f"<p>This link expires in {settings.RESET_TOKEN_EXPIRE_MINUTES} minutes.</p>"
            f"<p>If you did not request this, ignore this email.</p>"
        ),
    })

 
async def request_password_reset(db: AsyncSession, email: str) -> None:
    """
    Execute the forgot-password workflow.

    The function intentionally suppresses all internal failures to ensure
    the API response remains identical for both existing and non-existing
    email addresses.

    Args:
        db: Active database session.
        email: User email address.

    Returns:
        None
    """
    try:
        user = await _get_user_by_email(db, email)
 
        if user is None:
            logger.debug("Password reset requested for unknown email (suppressed)")
            return
 
        raw_token = await _create_reset_token(db, user)
        reset_link = _build_reset_link(raw_token)
 
        try:
            await _send_reset_email(user.email, reset_link)
        except Exception as email_exc:  # noqa: BLE001
            logger.error(
                "Failed to send password reset email to %s: %s",
                user.email,
                email_exc,
                exc_info=True,
            )
 
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Unexpected error during password reset request: %s",
            exc,
            exc_info=True,
        )
