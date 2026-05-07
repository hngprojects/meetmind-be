# tests/test_auth_reset_password.py

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, PasswordResetToken
from app.models.base import generate_uuid_v7


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _unique_email() -> str:
    """Generate a unique email for each test to avoid UNIQUE constraint errors."""
    return f"reset_{uuid.uuid4().hex[:8]}@meetmind.com"


async def create_test_user(db: AsyncSession) -> User:
    user = User(
        id=generate_uuid_v7(),
        email=_unique_email(),   # unique every call — no collision
        name="Reset Tester",
        password_hash="placeholder",
        is_verified=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def create_reset_token(
    db: AsyncSession,
    user_id,
    raw_token: str = "valid-raw-token",
    expires_in_minutes: int = 30,
    used: bool = False,
) -> PasswordResetToken:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes)
    record = PasswordResetToken(
        id=generate_uuid_v7(),
        user_id=user_id,
        token_hash=_hash_token(raw_token),
        expires_at=expires_at,
        used_at=datetime.now(timezone.utc) if used else None,
    )
    db.add(record)
    await db.commit()
    return record


RESET_URL = "/api/v1/auth/reset-password"


# ── Success ───────────────────────────────────────────────────────────────────

class TestResetPasswordSuccess:

    async def test_returns_200_with_valid_token(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """A valid token and strong password should return 200."""
        user = await create_test_user(db_session)
        await create_reset_token(db_session, user.id, raw_token="good-token-1")

        response = await client.post(
            RESET_URL,
            json={"token": "good-token-1", "new_password": "NewSecure1"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["message"] == "Password reset successfully"
        assert body["data"] is None

    async def test_token_cannot_be_reused_after_successful_reset(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """After a successful reset the same token must be rejected on a second attempt."""
        user = await create_test_user(db_session)
        await create_reset_token(db_session, user.id, raw_token="one-time-token-1")

        first = await client.post(
            RESET_URL,
            json={"token": "one-time-token-1", "new_password": "NewSecure1"},
        )
        assert first.status_code == 200

        second = await client.post(
            RESET_URL,
            json={"token": "one-time-token-1", "new_password": "AnotherPass2"},
        )
        assert second.status_code == 400


# ── Token failures ────────────────────────────────────────────────────────────

class TestResetPasswordTokenFailures:

    async def test_returns_400_with_nonexistent_token(self, client: AsyncClient):
        """A token that has no DB record must return 400."""
        response = await client.post(
            RESET_URL,
            json={"token": "does-not-exist-anywhere", "new_password": "NewSecure1"},
        )
        assert response.status_code == 400

    async def test_returns_400_with_expired_token(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """A token past its expiry must return 400."""
        user = await create_test_user(db_session)
        await create_reset_token(
            db_session,
            user.id,
            raw_token="expired-token-1",
            expires_in_minutes=-10,
        )

        response = await client.post(
            RESET_URL,
            json={"token": "expired-token-1", "new_password": "NewSecure1"},
        )
        assert response.status_code == 400

    async def test_returns_400_with_already_used_token(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """A token with used_at already set must return 400."""
        user = await create_test_user(db_session)
        await create_reset_token(
            db_session, user.id, raw_token="used-token-1", used=True
        )

        response = await client.post(
            RESET_URL,
            json={"token": "used-token-1", "new_password": "NewSecure1"},
        )
        assert response.status_code == 400

    async def test_all_failure_modes_return_same_message(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        Not-found, expired, and used tokens must all return the exact same
        message — no information leakage about which condition failed.
        """
        user = await create_test_user(db_session)

        await create_reset_token(
            db_session, user.id, raw_token="used-t-unique", used=True
        )
        await create_reset_token(
            db_session, user.id, raw_token="exp-t-unique", expires_in_minutes=-5
        )

        r_nonexistent = await client.post(
            RESET_URL,
            json={"token": "totally-fake-unique", "new_password": "NewSecure1"},
        )
        r_used = await client.post(
            RESET_URL,
            json={"token": "used-t-unique", "new_password": "NewSecure1"},
        )
        r_expired = await client.post(
            RESET_URL,
            json={"token": "exp-t-unique", "new_password": "NewSecure1"},
        )

        assert r_nonexistent.json()["message"] == r_used.json()["message"] == r_expired.json()["message"]


# ── Input validation ──────────────────────────────────────────────────────────

class TestResetPasswordValidation:

    async def test_returns_422_when_token_is_empty(self, client: AsyncClient):
        response = await client.post(
            RESET_URL, json={"token": "", "new_password": "NewSecure1"}
        )
        assert response.status_code == 422

    async def test_returns_422_when_password_too_short(self, client: AsyncClient):
        response = await client.post(
            RESET_URL, json={"token": "some-token", "new_password": "Ab1"}
        )
        assert response.status_code == 422

    async def test_returns_422_when_password_has_no_uppercase(self, client: AsyncClient):
        response = await client.post(
            RESET_URL, json={"token": "some-token", "new_password": "allowercase1"}
        )
        assert response.status_code == 422

    async def test_returns_422_when_password_has_no_lowercase(self, client: AsyncClient):
        response = await client.post(
            RESET_URL, json={"token": "some-token", "new_password": "NOLOWERCASE1"}
        )
        assert response.status_code == 422

    async def test_returns_422_when_password_has_no_digit(self, client: AsyncClient):
        response = await client.post(
            RESET_URL, json={"token": "some-token", "new_password": "NoNumbersHere"}
        )
        assert response.status_code == 422