"""
tests/test_auth_forgot_password.py

Tests for AUTH-FPW-05-BE — Forgot Password endpoint.

Run with:
    pytest tests/test_auth_forgot_password.py -v

All tests use the AsyncClient fixture from conftest.py and mock the database
and email service so they run without a live Postgres instance.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

ENDPOINT = "/api/v1/auth/forgot-password"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(email: str = "user@example.com") -> MagicMock:
    user = MagicMock()
    user.id = "019dfa1e-2a10-7dce-8acc-2890f11cfced"
    user.email = email
    return user


# ---------------------------------------------------------------------------
# AC 1-3: Input validation
# ---------------------------------------------------------------------------

class TestForgotPasswordValidation:
    async def test_forgot_password_returns_422_when_email_is_missing(self, client: AsyncClient) -> None:
        response = await client.post(ENDPOINT, json={})
        assert response.status_code == 422

    async def test_forgot_password_returns_422_when_email_is_empty(self, client: AsyncClient) -> None:
        response = await client.post(ENDPOINT, json={"email": ""})
        assert response.status_code == 422

    async def test_forgot_password_returns_422_when_email_is_whitespace(self, client: AsyncClient) -> None:
        response = await client.post(ENDPOINT, json={"email": "   "})
        assert response.status_code == 422

    async def test_forgot_password_returns_422_when_email_format_is_invalid(self, client: AsyncClient) -> None:
        response = await client.post(ENDPOINT, json={"email": "notanemail"})
        assert response.status_code == 422

    async def test_forgot_password_returns_422_when_email_has_no_tld(self, client: AsyncClient) -> None:
        response = await client.post(ENDPOINT, json={"email": "user@domain"})
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# AC 6-7: Safe generic response (account enumeration prevention)
# ---------------------------------------------------------------------------

class TestAccountEnumeration:
    async def test_forgot_password_returns_200_when_email_is_registered(self, client: AsyncClient) -> None:
        """Registered email: 200 with generic message."""
        with (
            patch(
                "app.services.auth._get_user_by_email",
                new_callable=AsyncMock,
                return_value=_make_user(),
            ),
            patch(
                "app.services.auth._create_reset_token",
                new_callable=AsyncMock,
                return_value="fake-raw-token",
            ),
            patch(
                "app.services.auth._send_reset_email",
                new_callable=AsyncMock,
            ),
        ):
            response = await client.post(ENDPOINT, json={"email": "user@example.com"})

        assert response.status_code == 200
        body = response.json()
        assert body["status_code"] == 200
        assert "reset link" in body["message"].lower()

    async def test_forgot_password_returns_200_when_email_is_not_registered(self, client: AsyncClient) -> None:
        """Unregistered email: MUST also return 200 with the exact same message."""
        with patch(
            "app.services.auth._get_user_by_email",
            new_callable=AsyncMock,
            return_value=None,  # user not found
        ):
            response = await client.post(ENDPOINT, json={"email": "ghost@example.com"})

        assert response.status_code == 200
        body = response.json()
        assert body["status_code"] == 200
        assert "reset link" in body["message"].lower()

    async def test_forgot_password_returns_identical_message_regardless_of_email_existence(
        self, client: AsyncClient
    ) -> None:
        """The message wording must be the same regardless of whether the account exists."""
        with (
            patch(
                "app.services.auth._get_user_by_email",
                new_callable=AsyncMock,
                return_value=_make_user(),
            ),
            patch("app.services.auth._create_reset_token", new_callable=AsyncMock, return_value="tok"),
            patch("app.services.auth._send_reset_email", new_callable=AsyncMock),
        ):
            r_registered = await client.post(ENDPOINT, json={"email": "user@example.com"})

        with patch(
            "app.services.auth._get_user_by_email",
            new_callable=AsyncMock,
            return_value=None,
        ):
            r_unregistered = await client.post(ENDPOINT, json={"email": "ghost@example.com"})

        assert r_registered.json()["message"] == r_unregistered.json()["message"]


# ---------------------------------------------------------------------------
# AC 4-5, 12: Token generation and expiry
# ---------------------------------------------------------------------------

class TestTokenGeneration:
    async def test_forgot_password_creates_token_when_user_exists(self, client: AsyncClient) -> None:
        create_token_mock = AsyncMock(return_value="fake-raw-token")

        with (
            patch("app.services.auth._get_user_by_email", new_callable=AsyncMock, return_value=_make_user()),
            patch("app.services.auth._create_reset_token", create_token_mock),
            patch("app.services.auth._send_reset_email", new_callable=AsyncMock),
        ):
            await client.post(ENDPOINT, json={"email": "user@example.com"})

        create_token_mock.assert_awaited_once()

    async def test_forgot_password_skips_token_creation_when_user_not_found(self, client: AsyncClient) -> None:
        create_token_mock = AsyncMock(return_value="should-not-be-called")

        with (
            patch("app.services.auth._get_user_by_email", new_callable=AsyncMock, return_value=None),
            patch("app.services.auth._create_reset_token", create_token_mock),
        ):
            await client.post(ENDPOINT, json={"email": "ghost@example.com"})

        create_token_mock.assert_not_awaited()


# ---------------------------------------------------------------------------
# AC 10, 14: Email and database failure handling
# ---------------------------------------------------------------------------

class TestFailureHandling:
    async def test_forgot_password_returns_200_when_email_service_fails(
        self, client: AsyncClient
    ) -> None:
        """Email delivery failure must not surface as an error to the caller."""
        with (
            patch("app.services.auth._get_user_by_email", new_callable=AsyncMock, return_value=_make_user()),
            patch("app.services.auth._create_reset_token", new_callable=AsyncMock, return_value="tok"),
            patch(
                "app.services.auth._send_reset_email",
                new_callable=AsyncMock,
                side_effect=Exception("SMTP connection refused"),
            ),
        ):
            response = await client.post(ENDPOINT, json={"email": "user@example.com"})

        assert response.status_code == 200

    async def test_forgot_password_returns_200_when_database_fails(
        self, client: AsyncClient
    ) -> None:
        """Database failure must not expose internals — safe 200 returned."""
        with patch(
            "app.services.auth._get_user_by_email",
            new_callable=AsyncMock,
            side_effect=Exception("connection pool exhausted"),
        ):
            response = await client.post(ENDPOINT, json={"email": "user@example.com"})

        # The service catches all exceptions and returns silently.
        # The endpoint always returns 200.
        assert response.status_code == 200

    async def test_forgot_password_response_contains_no_internal_error_detail(
        self, client: AsyncClient
    ) -> None:
        """Response body must never contain stack traces or internal messages."""
        with patch(
            "app.services.auth._get_user_by_email",
            new_callable=AsyncMock,
            side_effect=Exception("pg: relation users does not exist"),
        ):
            response = await client.post(ENDPOINT, json={"email": "user@example.com"})

        body_text = response.text.lower()
        assert "pg:" not in body_text
        assert "relation" not in body_text
        assert "traceback" not in body_text


# ---------------------------------------------------------------------------
# AC 11: Response shape lets frontend show a clear next step
# ---------------------------------------------------------------------------

class TestResponseShape:
    async def test_forgot_password_response_matches_api_envelope(self, client: AsyncClient) -> None:
        with (
            patch("app.services.auth._get_user_by_email", new_callable=AsyncMock, return_value=_make_user()),
            patch("app.services.auth._create_reset_token", new_callable=AsyncMock, return_value="tok"),
            patch("app.services.auth._send_reset_email", new_callable=AsyncMock),
        ):
            response = await client.post(ENDPOINT, json={"email": "user@example.com"})

        body = response.json()
        assert "status_code" in body
        assert "message" in body
        assert "data" in body
        assert body["data"] is None