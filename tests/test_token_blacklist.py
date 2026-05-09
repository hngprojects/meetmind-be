"""
Tests for access-token and refresh-token blacklisting after logout.

Flow under test
---------------
1.  Sign up  →  get access_token + refresh_token
2.  Logout   →  both tokens are blacklisted in the DB
3.  Attempt to use the old access_token on a protected route  →  401 token_revoked
4.  Attempt to use the old refresh_token to get a new pair   →  401

Each test registers a UNIQUE email (uuid-suffixed) so tests never collide
even though the in-memory SQLite database is shared across the session.

Run with:
    pytest tests/test_token_blacklist.py -v -s
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

# ── URL constants ──────────────────────────────────────────────────────────────

SIGNUP_URL  = "/api/v1/auth/signup"
LOGOUT_URL  = "/api/v1/auth/logout"
REFRESH_URL = "/api/v1/auth/refresh"
ME_URL      = "/api/v1/users/me"   # protected route — uses CurrentUser dep


# ── helpers ────────────────────────────────────────────────────────────────────

def unique_user(suffix: str | None = None) -> dict:
    """Return a signup payload with a guaranteed-unique email per test."""
    tag = suffix or uuid.uuid4().hex[:8]
    return {
        "name":     "Token Tester",
        "email":    f"blacklist_{tag}@example.com",
        "password": "SecurePass1!",
    }


async def signup_and_get_tokens(client: AsyncClient, user: dict) -> tuple[str, str]:
    """Register a user and return (access_token, refresh_token)."""
    response = await client.post(SIGNUP_URL, json=user)
    assert response.status_code == 201, (
        f"Signup failed unexpectedly: {response.status_code} — {response.json()}"
    )
    data = response.json()["data"]
    return data["access_token"], data["refresh_token"]


async def do_logout(
    client: AsyncClient,
    access_token: str,
    refresh_token: str,
    *,
    send_bearer: bool = True,
) -> None:
    """Call /logout. Pass send_bearer=False to omit the Authorization header."""
    headers = {"Authorization": f"Bearer {access_token}"} if send_bearer else {}
    response = await client.post(
        LOGOUT_URL,
        json={"refresh_token": refresh_token},
        headers=headers,
    )
    assert response.status_code == 200, (
        f"Logout failed unexpectedly: {response.status_code} — {response.json()}"
    )


# ── test suite ─────────────────────────────────────────────────────────────────

class TestTokenBlacklistingOnLogout:
    """End-to-end blacklist enforcement: sign up → logout → attempt reuse."""

    # ------------------------------------------------------------------
    # 1. Access token rejected after logout
    # ------------------------------------------------------------------

    @pytest.mark.anyio
    async def test_access_token_is_rejected_after_logout(self, client: AsyncClient):
        """
        GIVEN a valid access token issued at signup
        WHEN  the user logs out
        THEN  using that same access token on GET /users/me returns 401
              with error code 'token_revoked'

        Expected flow:
            POST /signup     → 201
            GET  /users/me   → 200  (token still live)
            POST /logout     → 200
            GET  /users/me   → 401  token_revoked
        """
        user = unique_user()
        access_token, refresh_token = await signup_and_get_tokens(client, user)

        # Confirm token works BEFORE logout
        pre = await client.get(ME_URL, headers={"Authorization": f"Bearer {access_token}"})
        print(f"\n  [pre-logout]  GET {ME_URL} → {pre.status_code}")
        assert pre.status_code == 200, (
            f"Expected 200 before logout but got {pre.status_code}. Body: {pre.json()}"
        )
        print("  [pre-logout]  Access token accepted before logout  ✓")

        await do_logout(client, access_token, refresh_token)
        print("  [logout]      POST /logout → 200  ✓")

        # Same token must now be rejected
        post = await client.get(ME_URL, headers={"Authorization": f"Bearer {access_token}"})
        body = post.json()
        print(f"  [post-logout] GET {ME_URL} → {post.status_code}  body={body}")

        assert post.status_code == 401, (
            f"Expected 401 after logout but got {post.status_code}. Body: {body}"
        )
        assert body.get("error", {}).get("code") == "token_revoked", (
            f"Expected error code 'token_revoked' but got '{body.get('error')}'. "
            f"Full body: {body}"
        )
        print("  [result]      Access token correctly rejected with 'token_revoked'  ✓")

    # ------------------------------------------------------------------
    # 2. Refresh token rejected after logout
    # ------------------------------------------------------------------

    @pytest.mark.anyio
    async def test_refresh_token_is_rejected_after_logout(self, client: AsyncClient):
        """
        GIVEN a valid refresh token issued at signup
        WHEN  the user logs out
        THEN  POST /refresh with that token returns 401

        Expected flow:
            POST /signup   → 201
            POST /logout   → 200
            POST /refresh  → 401
        """
        user = unique_user()
        access_token, refresh_token = await signup_and_get_tokens(client, user)

        await do_logout(client, access_token, refresh_token)
        print("\n  [logout]  POST /logout → 200  ✓")

        response = await client.post(REFRESH_URL, json={"refresh_token": refresh_token})
        body = response.json()
        print(f"  [refresh] POST {REFRESH_URL} → {response.status_code}  body={body}")

        assert response.status_code == 401, (
            f"Expected 401 when reusing a revoked refresh token but got "
            f"{response.status_code}. Body: {body}"
        )
        assert body.get("error", {}).get("code") == "invalid_refresh_token", (
            f"Expected error code 'invalid_refresh_token' but got '{body.get('error')}'. Full body: {body}"
        )
        print("  [result]  Refresh token correctly rejected after logout  ✓")

    # ------------------------------------------------------------------
    # 3. Double logout returns 401
    # ------------------------------------------------------------------

    @pytest.mark.anyio
    async def test_double_logout_returns_401(self, client: AsyncClient):
        """
        GIVEN a user has already logged out
        WHEN  they submit the same refresh token to /logout again
        THEN  the second call returns 401 — the token is already revoked

        Expected flow:
            POST /signup          → 201
            POST /logout (first)  → 200
            POST /logout (second) → 401
        """
        user = unique_user()
        access_token, refresh_token = await signup_and_get_tokens(client, user)

        await do_logout(client, access_token, refresh_token)
        print("\n  [first logout]  POST /logout → 200  ✓")

        # Second logout with the same tokens — refresh token is already revoked
        # in RefreshToken table so logout returns 401 before even touching blacklist
        second = await client.post(
            LOGOUT_URL,
            json={"refresh_token": refresh_token},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        body = second.json()
        print(f"  [second logout] POST /logout → {second.status_code}  body={body}")

        assert second.status_code == 401, (
            f"Expected 401 on double-logout but got {second.status_code}. Body: {body}"
        )
        assert body.get("error", {}).get("code") == "invalid_refresh_token", (
            f"Expected error code 'invalid_refresh_token' on double logout but got '{body.get('error')}'. Full body: {body}"
        )
        print("  [result]        Double logout correctly rejected with 401  ✓")

    # ------------------------------------------------------------------
    # 4. Logout does not affect another user's session
    # ------------------------------------------------------------------

    @pytest.mark.anyio
    async def test_logout_does_not_affect_other_sessions(self, client: AsyncClient):
        """
        GIVEN user A and user B each have a valid session
        WHEN  user A logs out
        THEN  user B's access token is still accepted on GET /users/me

        Expected flow:
            POST /signup (A)   → 201
            POST /signup (B)   → 201
            POST /logout (A)   → 200
            GET  /users/me (B) → 200  (not revoked)
        """
        a_access, a_refresh = await signup_and_get_tokens(client, unique_user("silo_a"))
        b_access, b_refresh = await signup_and_get_tokens(client, unique_user("silo_b"))

        await do_logout(client, a_access, a_refresh)
        print("\n  [user A logout] POST /logout → 200  ✓")

        resp = await client.get(ME_URL, headers={"Authorization": f"Bearer {b_access}"})
        body = resp.json()
        print(f"  [user B /me]    GET {ME_URL} → {resp.status_code}  body={body}")

        assert resp.status_code == 200, (
            f"User B's token was incorrectly affected by user A's logout. "
            f"Status: {resp.status_code}. Body: {body}"
        )
        assert body.get("error", {}).get("code") != "token_revoked", (
            f"User B's token was wrongly blacklisted. Body: {body}"
        )
        print("  [result]        User B's token unaffected by user A's logout  ✓")

        # Clean up
        await do_logout(client, b_access, b_refresh)

    # ------------------------------------------------------------------
    # 5. Logout without access token still revokes refresh token
    # ------------------------------------------------------------------

    @pytest.mark.anyio
    async def test_logout_without_access_token_still_revokes_refresh_token(
        self, client: AsyncClient
    ):
        """
        GIVEN a user sends /logout with only the refresh token (no Bearer header)
        WHEN  they later attempt to use the refresh token
        THEN  it is rejected with 401

        Covers API clients that don't store access tokens client-side.

        Expected flow:
            POST /signup                    → 201
            POST /logout (no Bearer header) → 200
            POST /refresh                   → 401
        """
        user = unique_user()
        access_token, refresh_token = await signup_and_get_tokens(client, user)

        # Logout with NO Authorization header — access jti blacklisting is skipped,
        # but the refresh token must still be revoked.
        await do_logout(client, access_token, refresh_token, send_bearer=False)
        print("\n  [logout (no Bearer)] POST /logout → 200  ✓")

        refresh_resp = await client.post(REFRESH_URL, json={"refresh_token": refresh_token})
        body = refresh_resp.json()
        print(
            f"  [refresh]            POST {REFRESH_URL} → {refresh_resp.status_code}"
            f"  body={body}"
        )

        assert refresh_resp.status_code == 401, (
            f"Expected 401 when reusing refresh token after logout-without-Bearer, "
            f"got {refresh_resp.status_code}. Body: {body}"
        )
        assert body.get("error", {}).get("code") == "invalid_refresh_token", (
            f"Expected error code 'invalid_refresh_token' but got '{body.get('error')}'. Full body: {body}"
        )
        print(
            "  [result]             Refresh token revoked even without "
            "access token in logout request  ✓"
        )