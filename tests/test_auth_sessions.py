"""Tests for AUTH-SES-07-BE: session token lifecycle."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy import select

from app.api.deps import get_current_user
from app.main import app
from app.models.user import ActiveSession, User
from app.services.auth import AuthService


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_user(**kwargs):
    user = MagicMock(spec=User)
    user.id = kwargs.get("id", uuid4())
    user.email = kwargs.get("email", "john@example.com")
    user.name = kwargs.get("name", "John Doe")
    user.role = kwargs.get("role", "member")
    user.is_verified = kwargs.get("is_verified", True)
    user.job_title = kwargs.get("job_title", "Engineer")
    return user


def override_current_user(user):
    """Return a dependency override that injects ``user`` as the current user."""
    async def _override():
        return user
    return _override


REFRESH_URL = "/api/v1/auth/refresh"
LOGOUT_URL  = "/api/v1/auth/logout"
ME_URL      = "/api/v1/auth/me"

ROTATE_SESSION   = "app.services.auth.AuthService.rotate_session"
REVOKE_SESSION   = "app.services.auth.AuthService.revoke_session"
CREATE_ACCESS    = "app.services.auth.AuthService.create_access_token"
DECODE_ACCESS    = "app.services.auth.AuthService.decode_access_token"

FAKE_ACCESS  = "fake.access.token"
FAKE_REFRESH = "fake.refresh.token"


# ── GET /auth/me ───────────────────────────────────────────────────────────────

class TestGetMe:
    @pytest.mark.anyio
    async def test_returns_200_with_valid_token(self, client: AsyncClient):
        """Authenticated user should receive their profile."""
        user = make_user()
        app.dependency_overrides[get_current_user] = override_current_user(user)

        response = await client.get(ME_URL)

        app.dependency_overrides.pop(get_current_user, None)
        body = response.json()
        assert response.status_code == 200
        assert body["message"] == "User retrieved successfully"
        assert body["data"]["email"] == user.email
        assert body["data"]["name"] == user.name
        assert body["data"]["next_step"] == "dashboard"

    @pytest.mark.anyio
    async def test_returns_401_without_token(self, client: AsyncClient):
        """No Authorization header should be rejected."""
        response = await client.get(ME_URL)
        assert response.status_code == 401

    @pytest.mark.anyio
    async def test_returns_401_with_invalid_token(self, client: AsyncClient):
        """Malformed token should be rejected."""
        from jose import JWTError
        with patch(DECODE_ACCESS, new_callable=AsyncMock, side_effect=JWTError):
            response = await client.get(
                ME_URL, headers={"Authorization": "Bearer bad.token"}
            )
        assert response.status_code == 401

    @pytest.mark.anyio
    async def test_next_step_is_verify_email_for_unverified_user(self, client: AsyncClient):
        """Unverified user should receive next_step='verify_email'."""
        user = make_user(is_verified=False)
        app.dependency_overrides[get_current_user] = override_current_user(user)

        response = await client.get(ME_URL)

        app.dependency_overrides.pop(get_current_user, None)
        assert response.status_code == 200
        assert response.json()["data"]["next_step"] == "verify_email"

    @pytest.mark.anyio
    async def test_next_step_is_onboarding_for_incomplete_profile(self, client: AsyncClient):
        """Verified user with missing job_title should receive next_step='onboarding'."""
        user = make_user(is_verified=True, job_title=None)
        app.dependency_overrides[get_current_user] = override_current_user(user)

        response = await client.get(ME_URL)

        app.dependency_overrides.pop(get_current_user, None)
        assert response.status_code == 200
        assert response.json()["data"]["next_step"] == "onboarding"

    @pytest.mark.anyio
    async def test_next_step_is_onboarding_when_name_missing(self, client: AsyncClient):
        """Verified user with no name should receive next_step='onboarding'."""
        user = make_user(is_verified=True, name=None)
        app.dependency_overrides[get_current_user] = override_current_user(user)

        response = await client.get(ME_URL)

        app.dependency_overrides.pop(get_current_user, None)
        assert response.status_code == 200
        assert response.json()["data"]["next_step"] == "onboarding"

    @pytest.mark.anyio
    async def test_response_contains_expected_fields(self, client: AsyncClient):
        """Response data must include all required fields."""
        user = make_user()
        app.dependency_overrides[get_current_user] = override_current_user(user)

        response = await client.get(ME_URL)

        app.dependency_overrides.pop(get_current_user, None)
        data = response.json()["data"]
        assert "id" in data
        assert "email" in data
        assert "name" in data
        assert "role" in data
        assert "is_verified" in data
        assert "next_step" in data


# ── POST /auth/refresh ─────────────────────────────────────────────────────────

class TestRefreshToken:
    @pytest.mark.anyio
    async def test_returns_200_with_valid_refresh_token(self, client: AsyncClient, db_session):
        """Valid refresh token should return a new access token."""
        user = User(email="refresh_test@example.com")
        db_session.add(user)
        await db_session.commit()

        token = await AuthService.create_session_aware_token(db_session, user)

        with patch.object(AuthService, "create_access_token", new_callable=AsyncMock, return_value=FAKE_ACCESS):
            response = await client.post(
                REFRESH_URL, json={"refresh_token": token}
            )

        assert response.status_code == 200
        body = response.json()
        assert body["message"] == "Token refreshed successfully"

    @pytest.mark.anyio
    async def test_returns_401_with_invalid_token(self, client: AsyncClient):
        """Malformed or expired refresh token should return 401."""
        with patch(ROTATE_SESSION, new_callable=AsyncMock, side_effect=Exception("JWTError")):
            response = await client.post(
                REFRESH_URL, json={"refresh_token": "bad.token"}
            )

        assert response.status_code == 401
        body = response.json()
        assert body["success"] is False
        assert body["error"]["code"] == "http_error"

    @pytest.mark.anyio
    async def test_returns_401_when_session_not_found(self, client: AsyncClient):
        """Refresh token whose session was deleted should return 401."""
        with patch(ROTATE_SESSION, new_callable=AsyncMock, return_value=None):
            response = await client.post(
                REFRESH_URL, json={"refresh_token": FAKE_REFRESH}
            )

        assert response.status_code == 401
        body = response.json()
        assert body["success"] is False
        assert body["error"]["code"] == "http_error"

    @pytest.mark.anyio
    async def test_returns_401_on_stolen_token_reuse(self, client: AsyncClient):
        """Token reuse after theft detection (all sessions wiped) should return 401."""
        with patch(ROTATE_SESSION, new_callable=AsyncMock, return_value=None):
            response = await client.post(
                REFRESH_URL, json={"refresh_token": "stolen.token"}
            )

        assert response.status_code == 401

    @pytest.mark.anyio
    async def test_returns_422_with_missing_refresh_token_field(self, client: AsyncClient):
        """Missing refresh_token field should return 422."""
        response = await client.post(REFRESH_URL, json={})
        assert response.status_code == 422


# ── POST /auth/logout ──────────────────────────────────────────────────────────

class TestLogout:
    @pytest.mark.anyio
    async def test_returns_200_and_revokes_session(self, client: AsyncClient):
        """Valid logout should delete the session and return 200."""
        user = make_user()
        app.dependency_overrides[get_current_user] = override_current_user(user)

        with patch(REVOKE_SESSION, new_callable=AsyncMock, return_value=True):
            response = await client.post(
                LOGOUT_URL, json={"refresh_token": FAKE_REFRESH}
            )

        app.dependency_overrides.pop(get_current_user, None)
        body = response.json()
        assert response.status_code == 200
        assert body["message"] == "Logged out successfully"

    @pytest.mark.anyio
    async def test_returns_401_without_access_token(self, client: AsyncClient):
        """No Authorization header should be rejected before revoke is called."""
        response = await client.post(
            LOGOUT_URL, json={"refresh_token": FAKE_REFRESH}
        )
        assert response.status_code == 401

    @pytest.mark.anyio
    async def test_is_idempotent_when_session_already_gone(self, client: AsyncClient):
        """Logging out twice should still return 200 — logout is idempotent."""
        user = make_user()
        app.dependency_overrides[get_current_user] = override_current_user(user)

        with patch(REVOKE_SESSION, new_callable=AsyncMock, return_value=False):
            response = await client.post(
                LOGOUT_URL, json={"refresh_token": FAKE_REFRESH}
            )

        app.dependency_overrides.pop(get_current_user, None)
        assert response.status_code == 200

    @pytest.mark.anyio
    async def test_returns_422_with_missing_refresh_token_field(self, client: AsyncClient):
        """Missing refresh_token field should return 422."""
        user = make_user()
        app.dependency_overrides[get_current_user] = override_current_user(user)

        response = await client.post(LOGOUT_URL, json={})

        app.dependency_overrides.pop(get_current_user, None)
        assert response.status_code == 422


# ── AuthService — service level (uses real SQLite db_session) ──────────────────

class TestAuthServiceCreateSessionAwareToken:
    @pytest.mark.anyio
    async def test_creates_active_session_row(self, db_session):
        """create_session_aware_token should insert a row into active_sessions."""
        user = User(email="session_test@example.com")
        db_session.add(user)
        await db_session.commit()

        await AuthService.create_session_aware_token(db_session, user)

        result = await db_session.execute(
            select(ActiveSession).where(ActiveSession.user_id == user.id)
        )
        session = result.scalar_one_or_none()
        assert session is not None

    @pytest.mark.anyio
    async def test_returns_jwt_string(self, db_session):
        """Returned token should be a non-empty string."""
        user = User(email="jwt_test@example.com")
        db_session.add(user)
        await db_session.commit()

        token = await AuthService.create_session_aware_token(db_session, user)

        assert isinstance(token, str)
        assert len(token) > 0

    @pytest.mark.anyio
    async def test_stores_hashed_token_not_raw(self, db_session):
        """The raw JWT must not be stored directly — only its hash."""
        user = User(email="hash_test@example.com")
        db_session.add(user)
        await db_session.commit()

        token = await AuthService.create_session_aware_token(db_session, user)

        result = await db_session.execute(
            select(ActiveSession).where(ActiveSession.user_id == user.id)
        )
        session = result.scalar_one_or_none()
        assert session.refresh_token_hash != token

    @pytest.mark.anyio
    async def test_token_payload_contains_session_id(self, db_session):
        """Decoded refresh JWT should carry the session_id claim."""
        user = User(email="payload_test@example.com")
        db_session.add(user)
        await db_session.commit()

        token = await AuthService.create_session_aware_token(db_session, user)
        payload = await AuthService.decode_refresh_token(token)

        assert "session_id" in payload
        assert payload["type"] == "refresh"
        assert payload["sub"] == str(user.id)


class TestAuthServiceRotateSession:
    @pytest.mark.anyio
    async def test_returns_session_and_updates_last_seen_at(self, db_session):
        """Valid token should return the session with updated last_seen_at."""
        user = User(email="rotate_test@example.com")
        db_session.add(user)
        await db_session.commit()

        token = await AuthService.create_session_aware_token(db_session, user)
        session = await AuthService.rotate_session(db_session, token)

        assert session is not None
        assert session.last_seen_at is not None

    @pytest.mark.anyio
    async def test_returns_none_for_nonexistent_session(self, db_session):
        """Token pointing to a deleted session should return None."""
        user = User(email="rotate_none@example.com")
        db_session.add(user)
        await db_session.commit()

        token = await AuthService.create_session_aware_token(db_session, user)

        # Delete the session to simulate logout before rotation
        result = await db_session.execute(
            select(ActiveSession).where(ActiveSession.user_id == user.id)
        )
        session = result.scalar_one_or_none()
        await db_session.delete(session)
        await db_session.commit()

        result = await AuthService.rotate_session(db_session, token)
        assert result is None

    @pytest.mark.anyio
    async def test_wipes_all_sessions_on_hash_mismatch(self, db_session):
        """Hash mismatch (stolen token) should delete all sessions for that user."""
        user = User(email="theft_test@example.com")
        db_session.add(user)
        await db_session.commit()

        # Create two sessions one at a time, committing after each so hashes are unique
        token1 = await AuthService.create_session_aware_token(db_session, user)
        token2 = await AuthService.create_session_aware_token(db_session, user)

        # Tamper with the stored hashes to simulate token theft
        result = await db_session.execute(
            select(ActiveSession).where(ActiveSession.user_id == user.id)
        )
        sessions = result.scalars().all()
        for s in sessions:
            s.refresh_token_hash = f"tampered_{s.id}"
        await db_session.commit()

        await AuthService.rotate_session(db_session, token2)

        # All sessions should be wiped
        remaining = await db_session.execute(
            select(ActiveSession).where(ActiveSession.user_id == user.id)
        )
        assert remaining.scalars().all() == []


class TestAuthServiceRevokeSession:
    @pytest.mark.anyio
    async def test_deletes_session_row(self, db_session):
        """revoke_session should delete the active session from the DB."""
        user = User(email="revoke_test@example.com")
        db_session.add(user)
        await db_session.commit()

        token = await AuthService.create_session_aware_token(db_session, user)
        result = await AuthService.revoke_session(db_session, token)

        assert result is True

        remaining = await db_session.execute(
            select(ActiveSession).where(ActiveSession.user_id == user.id)
        )
        assert remaining.scalar_one_or_none() is None

    @pytest.mark.anyio
    async def test_returns_false_when_session_already_gone(self, db_session):
        """Revoking an already-deleted session should return False without error."""
        user = User(email="revoke_gone@example.com")
        db_session.add(user)
        await db_session.commit()

        token = await AuthService.create_session_aware_token(db_session, user)

        # Revoke once
        await AuthService.revoke_session(db_session, token)

        # Revoke again — should not raise
        result = await AuthService.revoke_session(db_session, token)
        assert result is False

    @pytest.mark.anyio
    async def test_returns_false_for_invalid_token(self, db_session):
        """Passing a malformed token should return False without raising."""
        result = await AuthService.revoke_session(db_session, "not.a.valid.token")
        assert result is False