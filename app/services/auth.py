"""Authentication service: password hashing, user creation, JWT issuance."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Request, status
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import UserAlreadyExistsException
from app.core.responses import APIError
from app.models.user import ActiveSession, PasswordResetToken, RefreshToken, User
from app.schemas.auth import SignupRequest

# Pre-computed dummy hash for timing attack protection
_DUMMY_HASH: str = bcrypt.hashpw(b"__dummy__", bcrypt.gensalt()).decode()

RESET_TOKEN_EXPIRY_MINUTES = 60


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class AuthService:
    """Authentication service handling users, tokens, and sessions."""

    # -------------------------
    # Password utilities
    # -------------------------
    @staticmethod
    async def hash_password(password: str) -> str:
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode(), salt).decode()

    @staticmethod
    async def verify_password(password: str, hashed: str) -> bool:
        return bcrypt.checkpw(password.encode(), hashed.encode())

    # -------------------------
    # User management
    # -------------------------
    @staticmethod
    async def check_email_exists(email: str, db: AsyncSession) -> bool:
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def create_user(request: SignupRequest, db: AsyncSession) -> User:
        if await AuthService.check_email_exists(request.email, db):
            raise UserAlreadyExistsException(email=request.email)

        user = User(
            name=request.name,
            email=request.email,
            password_hash=await AuthService.hash_password(request.password),
        )
        db.add(user)
        await db.flush()
        return user

    # -------------------------
    # JWT tokens
    # -------------------------
    @staticmethod
    async def create_access_token(user: User) -> str:
        expire = _now() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        payload = {
            "sub": str(user.id),
            "name": user.name,
            "email": user.email,
            "exp": expire,
            "iat": _now(),
            "type": "access",
        }
        return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

    @staticmethod
    async def decode_access_token(token: str) -> dict:
        return jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )

    @staticmethod
    async def decode_refresh_token(token: str) -> dict:
        return jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )

    # -------------------------
    # Refresh token (DB-backed)
    # -------------------------
    @staticmethod
    async def create_refresh_token(
        db: AsyncSession,
        user_id: uuid.UUID,
        ip_address: str | None = None,
        device_hint: str | None = None,
    ) -> tuple[str, datetime]:
        raw = secrets.token_urlsafe(48)
        token_hash = _hash_token(raw)
        now = _now()
        expires_at = now + timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES)

        db.add(RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        ))
        db.add(ActiveSession(
            user_id=user_id,
            refresh_token_hash=token_hash,
            ip_address=ip_address,
            device_hint=device_hint,
            last_seen_at=now,
        ))
        await db.commit()

        return raw, expires_at

    # -------------------------
    # Session-aware refresh tokens (JWT-based sessions)
    # -------------------------
    @staticmethod
    async def create_session_aware_token(
        db: AsyncSession,
        user: User,
        request: Request | None = None,
    ) -> str:
        session = ActiveSession(
            user_id=user.id,
            refresh_token_hash="pending",
            device_hint=request.headers.get("user-agent", "")[:120] if request else None,
            ip_address=request.client.host if request else None,
            last_seen_at=_now(),
        )
        db.add(session)
        await db.flush()

        expire = _now() + timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES)
        payload = {
            "sub": str(user.id),
            "session_id": str(session.id),
            "exp": expire,
            "iat": _now(),
            "type": "refresh",
        }

        raw_jwt = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
        session.refresh_token_hash = _hash_token(raw_jwt)

        await db.commit()
        return raw_jwt

    @staticmethod
    async def rotate_session(db: AsyncSession, refresh_token: str) -> ActiveSession | None:
        payload = await AuthService.decode_refresh_token(refresh_token)

        session_id = uuid.UUID(payload["session_id"])
        user_id = uuid.UUID(payload["sub"])

        result = await db.execute(select(ActiveSession).where(ActiveSession.id == session_id))
        session = result.scalar_one_or_none()

        if not session:
            return None

        if session.refresh_token_hash != _hash_token(refresh_token):
            # token reuse detected → revoke all sessions
            all_sessions = await db.execute(
                select(ActiveSession).where(ActiveSession.user_id == user_id)
            )
            for s in all_sessions.scalars().all():
                await db.delete(s)
            await db.commit()
            return None

        session.last_seen_at = _now()
        await db.commit()
        return session

    @staticmethod
    async def revoke_session(db: AsyncSession, refresh_token: str) -> bool:
        try:
            payload = await AuthService.decode_refresh_token(refresh_token)
            session_id = uuid.UUID(payload["session_id"])
        except Exception:
            return False

        result = await db.execute(
            select(ActiveSession).where(ActiveSession.id == session_id)
        )
        session = result.scalar_one_or_none()

        if session:
            await db.delete(session)
            await db.commit()
            return True

        return False

    # -------------------------
    # Login
    # -------------------------
    @staticmethod
    async def login(email: str, password: str, db: AsyncSession) -> User:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        stored_hash = user.password_hash if (user and user.password_hash) else _DUMMY_HASH
        password_ok = await AuthService.verify_password(password, stored_hash)

        if not user or not user.password_hash or not password_ok:
            raise APIError(
                "Invalid email or password",
                status_code=status.HTTP_401_UNAUTHORIZED,
                code="invalid_credentials",
            )

        return user

    # -------------------------
    # Password reset
    # -------------------------
    @staticmethod
    async def create_password_reset_token(db: AsyncSession, user: User) -> str:
        result = await db.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.used_at.is_(None),
            )
        )

        now = _now()
        for old in result.scalars().all():
            old.used_at = now

        raw = secrets.token_urlsafe(48)
        token_hash = _hash_token(raw)
        expires_at = now + timedelta(minutes=RESET_TOKEN_EXPIRY_MINUTES)

        db.add(PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
        ))

        await db.commit()
        return raw

    @staticmethod
    async def reset_password(raw_token: str, new_password: str, db: AsyncSession) -> None:
        token_hash = _hash_token(raw_token)

        result = await db.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.token_hash == token_hash
            )
        )
        rt = result.scalar_one_or_none()

        _invalid = APIError(
            "This reset link is invalid or has expired.",
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid_reset_token",
        )

        if not rt or rt.used_at:
            raise _invalid

        expires_at = rt.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at < _now():
            raise _invalid

        result = await db.execute(select(User).where(User.id == rt.user_id))
        user = result.scalar_one_or_none()

        if not user:
            raise _invalid

        user.password_hash = await AuthService.hash_password(new_password)
        rt.used_at = _now()

        await db.commit()

    # -------------------------
    # Session helpers
    # -------------------------
    @staticmethod
    def get_next_step(user: User) -> str:
        if not user.is_verified:
            return "verify_email"
        if not user.job_title or not user.company:
            return "onboarding"
        return "dashboard"

    @staticmethod
    async def refresh_access_token(
        raw_token: str,
        db: AsyncSession,
        ip_address: str | None = None,
    ) -> dict:
        token_hash = _hash_token(raw_token)

        result = await db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        rt = result.scalar_one_or_none()

        _unauthorized = APIError(
            "Invalid or expired refresh token",
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="unauthorized",
        )

        if not rt or rt.revoked or rt.expires_at < _now():
            raise _unauthorized

        result = await db.execute(select(User).where(User.id == rt.user_id))
        user = result.scalar_one_or_none()

        if not user:
            raise _unauthorized

        new_raw = secrets.token_urlsafe(48)
        new_hash = _hash_token(new_raw)
        now = _now()

        new_expires = now + timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES)

        db.add(RefreshToken(
            user_id=rt.user_id,
            token_hash=new_hash,
            expires_at=new_expires,
        ))

        rt.revoked = True

        session_result = await db.execute(
            select(ActiveSession).where(
                ActiveSession.refresh_token_hash == token_hash
            )
        )
        session = session_result.scalar_one_or_none()

        if session:
            session.refresh_token_hash = new_hash
            session.last_seen_at = now
            if ip_address:
                session.ip_address = ip_address
        else:
            db.add(ActiveSession(
                user_id=rt.user_id,
                refresh_token_hash=new_hash,
                ip_address=ip_address,
                last_seen_at=now,
            ))

        await db.commit()

        access_token = await AuthService.create_access_token(user)

        return {
            "access_token": access_token,
            "refresh_token": new_raw,
            "user": user,
        }

    @staticmethod
    async def logout(raw_token: str, db: AsyncSession) -> None:
        token_hash = _hash_token(raw_token)

        result = await db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        rt = result.scalar_one_or_none()

        if not rt:
            raise APIError(
                "Invalid refresh token",
                status_code=status.HTTP_401_UNAUTHORIZED,
                code="invalid_refresh_token",
            )

        rt.revoked = True

        session_result = await db.execute(
            select(ActiveSession).where(
                ActiveSession.refresh_token_hash == token_hash
            )
        )
        session = session_result.scalar_one_or_none()

        if session:
            await db.delete(session)

        await db.commit()