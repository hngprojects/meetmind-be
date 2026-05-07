"""Pydantic schemas for authentication request and response payloads."""

from __future__ import annotations
import re
from pydantic import BaseModel, EmailStr, Field, field_validator


import re


class ForgotPasswordRequest(BaseModel):
    """Payload for requesting a password reset link."""

    email: EmailStr = Field(..., max_length=255)


class ResetPasswordRequest(BaseModel):
    """Payload for submitting a new password using a reset token."""

    token: str = Field(..., min_length=1)
    password: str = Field(..., min_length=8, max_length=255)

    @field_validator("token")
    @classmethod
    def validate_token_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Token cannot be empty or whitespace-only")
        return v.strip()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Password cannot be empty or whitespace-only")
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)

    @field_validator("password")
    @classmethod
    def validate_password_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Password cannot be empty or whitespace-only")
        return v


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class SignupRequest(BaseModel):
    """Payload for registering a new user account.

    Attributes:
        name: User's display name. Stripped of surrounding whitespace.
        email: A syntactically valid email address.
        password: Plaintext password meeting strength requirements
            enforced by :meth:`validate_password`.
    """

    name: str = Field(..., max_length=120, description="User's full name")
    email: EmailStr = Field(..., max_length=255, description="User's email address")
    password: str = Field(
        ..., min_length=8, max_length=255, description="User's password"
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Reject empty/whitespace-only names, strip surrounding spaces, and
        block HTML/script injection characters.

        Args:
            v: Raw ``name`` value from the request body.

        Returns:
            The trimmed name string.

        Raises:
            ValueError: If the name is empty, whitespace-only, or contains
                unsafe characters (``< > { } & " '``).
        """
        if not v or not v.strip():
            raise ValueError("Name cannot be empty or whitespace-only")
        stripped = v.strip()
        if re.search(r"[<>{}&\"']", stripped):
            raise ValueError("Name contains invalid characters")
        return stripped

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Enforce minimum password strength rules.

        Requires at least 8 characters with at least one uppercase letter,
        one lowercase letter, and one digit.

        Args:
            v: Raw ``password`` value from the request body.

        Returns:
            The password unchanged when it satisfies the rules.

        Raises:
            ValueError: When any rule is violated. The message identifies
                the specific rule that failed.
        """
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        return v



# ──  schemas for session lifecycle (AUTH-SES-07-BE) ─────────────────────────

class SigninRequest(BaseModel):
    """Payload for authenticating an existing user account.

    Attributes:
        email: The email address the user registered with.
        password: The plaintext password to verify against the stored hash.
    """

    email: EmailStr = Field(..., max_length=255, description="User's email address")
    password: str = Field(..., max_length=255, description="User's password")


class RefreshRequest(BaseModel):
    """Payload for rotating an access token using a refresh token.

    Attributes:
        refresh_token: The signed refresh JWT previously issued on login.
            Must be valid, unexpired, and map to an existing active session.
    """

    refresh_token: str = Field(..., description="Refresh JWT issued at login")


class LogoutRequest(BaseModel):
    """Payload for terminating the current session.

    Attributes:
        refresh_token: The refresh JWT whose session row should be deleted.
            The access token is validated separately via the Authorization
            header; this token identifies which session to revoke.
    """

    refresh_token: str = Field(..., description="Refresh JWT to be revoked")


class TokenData(BaseModel):
    """Token pair returned immediately after a successful login.

    Both the access token and refresh token are issued together. The
    access token is short-lived and used to authenticate requests. The
    refresh token is long-lived and used only to obtain new access tokens.

    Attributes:
        access_token: Signed JWT for authenticating API requests. Include
            in the ``Authorization: Bearer <token>`` header.
        refresh_token: Signed JWT for obtaining new access tokens via
            ``POST /auth/refresh``. Store securely; treat as a secret.
        token_type: Always ``"bearer"``.
        expires_in: Lifetime of the access token in seconds.
    """

    access_token: str = Field(..., description="Short-lived JWT for API access")
    refresh_token: str = Field(..., description="Long-lived JWT for token rotation")
    token_type: str = Field(default="bearer", description="Token scheme")
    expires_in: int = Field(..., description="Access token lifetime in seconds")


class AccessTokenData(BaseModel):
    """New access token returned after a successful token rotation.

    Only the access token is reissued on rotation. The refresh token and
    its session row are preserved and updated with a fresh ``last_seen_at``
    timestamp.

    Attributes:
        access_token: The newly issued JWT for authenticating API requests.
        token_type: Always ``"bearer"``.
        expires_in: Lifetime of the new access token in seconds.
    """

    access_token: str = Field(..., description="Newly issued JWT for API access")
    token_type: str = Field(default="bearer", description="Token scheme")
    expires_in: int = Field(..., description="Access token lifetime in seconds")


class UserData(BaseModel):
    """Current user profile returned from ``GET /auth/me``.

    Attributes:
        id: UUID of the user record as a string.
        name: User's display name, or ``None`` if not yet set.
        email: The verified email address on the account.
        role: Permission role assigned to the user, or ``None`` if unset.
        is_verified: Whether the user has confirmed their email address.
        next_step: Routing hint for the frontend. One of:

            - ``"verify_email"`` — account exists but email is unconfirmed.
            - ``"onboarding"`` — verified but profile is incomplete.
            - ``"dashboard"`` — fully set up; proceed to the main app.
    """

    id: str = Field(..., description="User UUID as a string")
    name: str | None = Field(None, description="User's display name")
    email: str = Field(..., description="User's email address")
    role: str | None = Field(None, description="User's permission role")
    is_verified: bool = Field(..., description="Whether the email is confirmed")
    next_step: str = Field(
        ..., description="Frontend routing hint: dashboard | onboarding | verify_email"
    )