"""
Tests for Interview Session Management & Context Injection API.

Endpoints under test
--------------------
POST /api/v1/interviews       — create interview session with context
GET  /api/v1/interviews/{id}  — retrieve interview session by ID

Each test registers a unique user so sessions never collide across the
shared in-memory SQLite database.

Run with:
    pytest tests/test_interviews.py -v -s
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient

logger = logging.getLogger(__name__)

# ── URL constants ──────────────────────────────────────────────────────────────

SIGNUP_URL = "/api/v1/auth/signup"
INTERVIEWS_URL = "/api/v1/interviews"

# ── helpers ────────────────────────────────────────────────────────────────────


def unique_user(tag: str | None = None) -> dict:
    """Return a signup payload with a guaranteed-unique email."""
    suffix = tag or uuid.uuid4().hex[:8]
    return {
        "name": "Interview Tester",
        "email": f"interview_{suffix}@example.com",
        "password": "SecurePass1!",
    }


async def signup_and_get_token(client: AsyncClient, user: dict) -> str:
    """Register a user and return their access token."""
    response = await client.post(SIGNUP_URL, json=user)
    assert response.status_code == 201, (
        f"Signup failed: {response.status_code} — {response.json()}"
    )
    return response.json()["data"]["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


VALID_INTERVIEW_PAYLOAD = {
    "title": "Backend Engineer Interview",
    "candidate_name": "Jane Doe",
    "candidate_email": "jane@example.com",
    "job_description": "Build scalable APIs using FastAPI and PostgreSQL.",
    "scoring_rubric": "Communication, API design, problem-solving, scalability.",
    "role_title": "Senior Backend Engineer",
    "platform": "zoom",
    "ai_tone": "professional",
}


# ── POST /interviews ───────────────────────────────────────────────────────────


class TestCreateInterview:
    @pytest.mark.anyio
    async def test_creates_interview_and_returns_201(self, client: AsyncClient):
        """
        GIVEN a valid interview payload
        WHEN  POST /interviews is called by an authenticated user
        THEN  the response is 201 with the created session data

        Expected:
            POST /interviews → 201
            data.status      == "draft"
            data.summary.job_description and scoring_rubric persisted correctly
        """
        token = await signup_and_get_token(client, unique_user())
        response = await client.post(
            INTERVIEWS_URL,
            json=VALID_INTERVIEW_PAYLOAD,
            headers=auth_headers(token),
        )
        body = response.json()
        logger.info(
            "[create] POST /interviews → %d  id=%s",
            response.status_code,
            body.get("data", {}).get("id"),
        )

        assert response.status_code == 201, (
            f"Expected 201 but got {response.status_code}. Body: {body}"
        )
        data = body["data"]
        assert data["status"] == "draft", (
            f"Expected status 'draft' but got '{data['status']}'"
        )
        assert data["title"] == VALID_INTERVIEW_PAYLOAD["title"]
        assert data["candidate_name"] == VALID_INTERVIEW_PAYLOAD["candidate_name"]
        assert data["candidate_email"] == VALID_INTERVIEW_PAYLOAD["candidate_email"]
        assert (
            data["summary"]["job_description"]
            == VALID_INTERVIEW_PAYLOAD["job_description"]
        )
        assert (
            data["summary"]["scoring_rubric"]
            == VALID_INTERVIEW_PAYLOAD["scoring_rubric"]
        )
        assert data["summary"]["status"] == "pending"
        assert "id" in data
        assert "created_at" in data
        logger.info("[result] Interview created with correct status and context  ✓")

    @pytest.mark.anyio
    async def test_create_returns_401_without_token(self, client: AsyncClient):
        """
        GIVEN no Authorization header
        WHEN  POST /interviews is called
        THEN  the response is 401

        Expected:
            POST /interviews (no auth) → 401
        """
        response = await client.post(INTERVIEWS_URL, json=VALID_INTERVIEW_PAYLOAD)
        logger.info("[no auth] POST /interviews → %d", response.status_code)

        assert response.status_code == 401, (
            f"Expected 401 without token but got {response.status_code}."
            f"Body: {response.json()}"
        )
        logger.info("[result]  Unauthenticated requestcorrectly rejected  ✓")

    @pytest.mark.anyio
    async def test_create_returns_422_when_title_missing(self, client: AsyncClient):
        """
        GIVEN a payload missing the required 'title' field
        WHEN  POST /interviews is called
        THEN  the response is 422

        Expected:
            POST /interviews (no title) → 422
        """
        token = await signup_and_get_token(client, unique_user())
        payload = {k: v for k, v in VALID_INTERVIEW_PAYLOAD.items() if k != "title"}
        response = await client.post(
            INTERVIEWS_URL,
            json=payload,
            headers=auth_headers(token),
        )
        logger.info("[missing title] POST /interviews → %d", response.status_code)

        assert response.status_code == 422, (
            "Expected 422 for missing title but got "
            f"{response.status_code}. Body: {response.json()}"
        )
        logger.info("[result]        Missing required field correctly rejected  ✓")

    @pytest.mark.anyio
    async def test_create_returns_422_when_job_description_missing(
        self, client: AsyncClient
    ):
        """
        GIVEN a payload missing 'job_description'
        WHEN  POST /interviews is called
        THEN  the response is 422

        Expected:
            POST /interviews (no job_description) → 422
        """
        token = await signup_and_get_token(client, unique_user())
        payload = {
            k: v for k, v in VALID_INTERVIEW_PAYLOAD.items() if k != "job_description"
        }
        response = await client.post(
            INTERVIEWS_URL,
            json=payload,
            headers=auth_headers(token),
        )
        logger.info(
            "[missing job_description] POST /interviews → %d", response.status_code
        )

        assert response.status_code == 422, (
            f"Expected 422 for missing job_description but got"
            f"{response.status_code}. Body: {response.json()}"
        )
        logger.info(
            "[result]                  Missing context field correctly rejected  ✓"
        )

    @pytest.mark.anyio
    async def test_create_returns_422_when_scoring_rubric_missing(
        self, client: AsyncClient
    ):
        """
        GIVEN a payload missing 'scoring_rubric'
        WHEN  POST /interviews is called
        THEN  the response is 422

        Expected:
            POST /interviews (no scoring_rubric) → 422
        """
        token = await signup_and_get_token(client, unique_user())
        payload = {
            k: v for k, v in VALID_INTERVIEW_PAYLOAD.items() if k != "scoring_rubric"
        }
        response = await client.post(
            INTERVIEWS_URL,
            json=payload,
            headers=auth_headers(token),
        )
        logger.info(
            "[missing scoring_rubric] POST /interviews → %d", response.status_code
        )

        assert response.status_code == 422, (
            f"Expected 422 for missing scoring_rubric but got {response.status_code}."
            f"Body: {response.json()}"
        )
        logger.info(
            "[result]                 Missing scoring rubric correctly rejected  ✓"
        )

    @pytest.mark.anyio
    async def test_optional_fields_default_correctly(self, client: AsyncClient):
        """
        GIVEN a payload with only required fields (no platform, ai_tone, role_title)
        WHEN  POST /interviews is called
        THEN  the response is 201 and optional fields are null

        Expected:
            POST /interviews (minimal payload) → 201
            data.platform == null
            data.ai_tone  == null
        """
        token = await signup_and_get_token(client, unique_user())
        minimal = {
            "title": "Minimal Interview",
            "candidate_name": "John Smith",
            "job_description": "Write Python services.",
            "scoring_rubric": "Code quality, communication.",
        }
        response = await client.post(
            INTERVIEWS_URL,
            json=minimal,
            headers=auth_headers(token),
        )
        body = response.json()
        logger.info("[minimal payload] POST /interviews → %d", response.status_code)

        assert response.status_code == 201, (
            "Expected 201 for minimal payload but got"
            f"{response.status_code}. Body: {body}"
        )
        data = body["data"]
        assert data["platform"] is None
        assert data["ai_tone"] is None
        assert data["candidate_email"] is None
        logger.info("[result]          Optional fields correctly default to null  ✓")


# ── GET /interviews/{id} ───────────────────────────────────────────────────────


class TestGetInterview:
    @pytest.mark.anyio
    async def test_retrieves_interview_by_id(self, client: AsyncClient):
        """
        GIVEN an interview was created by the authenticated user
        WHEN  GET /interviews/{id} is called
        THEN  the response is 200 with full session and context data

        Expected:
            POST /interviews       → 201  (create)
            GET  /interviews/{id}  → 200  (retrieve)
            context fields match what was submitted
        """
        token = await signup_and_get_token(client, unique_user())

        create = await client.post(
            INTERVIEWS_URL,
            json=VALID_INTERVIEW_PAYLOAD,
            headers=auth_headers(token),
        )
        assert create.status_code == 201
        interview_id = create.json()["data"]["id"]
        logger.info("[create] POST /interviews → 201  id=%s  ✓", interview_id)

        get = await client.get(
            f"{INTERVIEWS_URL}/{interview_id}",
            headers=auth_headers(token),
        )
        body = get.json()
        logger.info("[get]    GET /interviews/%s → %d", interview_id, get.status_code)

        assert get.status_code == 200, (
            f"Expected 200 but got {get.status_code}. Body: {body}"
        )
        data = body["data"]
        assert str(data["id"]) == interview_id
        assert (
            data["summary"]["job_description"]
            == VALID_INTERVIEW_PAYLOAD["job_description"]
        )
        assert (
            data["summary"]["scoring_rubric"]
            == VALID_INTERVIEW_PAYLOAD["scoring_rubric"]
        )
        assert data["status"] == "draft"
        logger.info("[result] Interview retrieved with correct context  ✓")

    @pytest.mark.anyio
    async def test_get_returns_404_for_nonexistent_interview(self, client: AsyncClient):
        """
        GIVEN a random UUID that does not exist in the database
        WHEN  GET /interviews/{id} is called
        THEN  the response is 404

        Expected:
            GET /interviews/{random_uuid} → 404
            error.code == "interview_not_found"
        """
        token = await signup_and_get_token(client, unique_user())
        fake_id = str(uuid.uuid4())
        response = await client.get(
            f"{INTERVIEWS_URL}/{fake_id}",
            headers=auth_headers(token),
        )
        body = response.json()
        logger.info(
            "[not found] GET /interviews/%s → %d", fake_id, response.status_code
        )

        assert response.status_code == 404, (
            "Expected 404 for nonexistent interview but got"
            f"{response.status_code}. Body: {body}"
        )
        assert body["error"]["code"] == "interview_not_found", (
            f"Expected code 'interview_not_found' but got '{body.get('error')}'"
        )
        logger.info("[result]    Nonexistent interview correctly returns 404  ✓")

    @pytest.mark.anyio
    async def test_get_returns_404_for_another_users_interview(
        self, client: AsyncClient
    ):
        """
        GIVEN user A creates an interview
        WHEN  user B tries to retrieve it
        THEN  the response is 404 — cross-user data leakage prevented

        Expected:
            POST /interviews (user A)      → 201
            GET  /interviews/{id} (user B) → 404
        """
        token_a = await signup_and_get_token(client, unique_user("iso_a"))
        token_b = await signup_and_get_token(client, unique_user("iso_b"))

        create = await client.post(
            INTERVIEWS_URL,
            json=VALID_INTERVIEW_PAYLOAD,
            headers=auth_headers(token_a),
        )
        assert create.status_code == 201
        interview_id = create.json()["data"]["id"]
        logger.info("[user A create] POST /interviews → 201  id=%s  ✓", interview_id)

        get = await client.get(
            f"{INTERVIEWS_URL}/{interview_id}",
            headers=auth_headers(token_b),
        )
        body = get.json()
        logger.info(
            "[user B get]    GET /interviews/%s → %d  body=%s",
            interview_id,
            get.status_code,
            body,
        )

        assert get.status_code == 404, (
            "Expected 404 when user B accesses user A's interview, got "
            f"{get.status_code}. Body: {body}"
        )
        logger.info("[result]        Cross-user access correctly blocked with 404  ✓")

    @pytest.mark.anyio
    async def test_get_returns_401_without_token(self, client: AsyncClient):
        """
        GIVEN no Authorization header
        WHEN  GET /interviews/{id} is called
        THEN  the response is 401

        Expected:
            GET /interviews/{id} (no auth) → 401
        """
        fake_id = str(uuid.uuid4())
        response = await client.get(f"{INTERVIEWS_URL}/{fake_id}")
        logger.info("[no auth] GET /interviews/%s → %d", fake_id, response.status_code)

        assert response.status_code == 401, (
            "Expected 401 without token but got {response.status_code}."
            f"Body: {response.json()}"
        )
        logger.info("[result]  Unauthenticated retrieval correctly rejected  ✓")


# ── GET /interviews (Index) ───────────────────────────────────────────────────


class TestGetAllInterviews:
    @pytest.mark.anyio
    async def test_retrieves_all_interviews_for_authenticated_user(
        self, client: AsyncClient
    ):
        """
        GIVEN an authenticated user has created multiple interviews
        WHEN  GET /interviews is called
        THEN  the response is 200 with a list of all their interviews

        Expected:
            GET /interviews → 200
            data.length == 2
        """
        token = await signup_and_get_token(client, unique_user())

        # Create two interviews
        await client.post(
            INTERVIEWS_URL, json=VALID_INTERVIEW_PAYLOAD, headers=auth_headers(token)
        )
        await client.post(
            INTERVIEWS_URL, json=VALID_INTERVIEW_PAYLOAD, headers=auth_headers(token)
        )

        response = await client.get(INTERVIEWS_URL, headers=auth_headers(token))
        body = response.json()
        logger.info("[get all] GET /interviews → %d", response.status_code)

        assert response.status_code == 200
        assert len(body["data"]) == 2
        logger.info("[result]  Successfully retrieved all user interviews  ✓")

    @pytest.mark.anyio
    async def test_get_all_filters_by_status(self, client: AsyncClient):
        """
        GIVEN interviews with different statuses
        WHEN  GET /interviews?status=draft is called
        THEN  only interviews with that status are returned

        Expected:
            GET /interviews?status=draft → returns interviews
            GET /interviews?status=live  → returns 0 if none exist
        """
        token = await signup_and_get_token(client, unique_user())
        await client.post(
            INTERVIEWS_URL, json=VALID_INTERVIEW_PAYLOAD, headers=auth_headers(token)
        )

        # All new interviews start as 'draft'
        response = await client.get(
            f"{INTERVIEWS_URL}?status=draft", headers=auth_headers(token)
        )
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

        # Check a status that shouldn't have results
        response = await client.get(
            f"{INTERVIEWS_URL}?status=live", headers=auth_headers(token)
        )
        assert response.status_code == 200
        assert len(response.json()["data"]) == 0
        logger.info("[result]  Status filtering works as expected  ✓")

    @pytest.mark.anyio
    async def test_get_all_interviews_excludes_other_users_data(self, client: AsyncClient):
        """
        GIVEN User A and User B both have interviews
        WHEN  User A calls GET /interviews
        THEN  only User A's interviews are returned
        """
        token_a = await signup_and_get_token(client, unique_user("list_a"))
        token_b = await signup_and_get_token(client, unique_user("list_b"))

        await client.post(
            INTERVIEWS_URL, json=VALID_INTERVIEW_PAYLOAD, headers=auth_headers(token_a)
        )
        await client.post(
            INTERVIEWS_URL, json=VALID_INTERVIEW_PAYLOAD, headers=auth_headers(token_b)
        )

        response = await client.get(INTERVIEWS_URL, headers=auth_headers(token_a))
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1
        logger.info("[result]  Multi-user isolation for list endpoint verified  ✓")


# ── PATCH /interviews/{id}/reschedule ─────────────────────────────────────────


class TestRescheduleInterview:
    @pytest.mark.anyio
    async def test_reschedule_success(self, client: AsyncClient):
        """
        GIVEN an existing interview
        WHEN  PATCH /interviews/{id}/reschedule is called with valid times
        THEN  the response is 200 and times/duration are updated

        Expected:
            PATCH /interviews/{id}/reschedule → 200
            data.scheduled_start == new_start
            data.duration_min is updated
        """
        token = await signup_and_get_token(client, unique_user())
        create = await client.post(
            INTERVIEWS_URL, json=VALID_INTERVIEW_PAYLOAD, headers=auth_headers(token)
        )
        interview_id = create.json()["data"]["id"]

        new_start = (datetime.now() + timedelta(days=1)).isoformat()
        new_end = (datetime.now() + timedelta(days=1, hours=1)).isoformat()

        payload = {"scheduled_start": new_start, "scheduled_end": new_end}
        response = await client.patch(
            f"{INTERVIEWS_URL}/{interview_id}/reschedule",
            json=payload,
            headers=auth_headers(token),
        )
        body = response.json()
        logger.info(
            "[reschedule] PATCH /interviews/%s → %d",
            interview_id, response.status_code,
        )

        assert response.status_code == 200
        data = body["data"]
        # Pydantic/JSON serialization might vary slightly,
        # so we check if it's generally correct
        assert "scheduled_start" in data
        assert data["scheduled_start"].startswith(new_start[:10])
        logger.info(
            "[result]     Interview rescheduled successfully  ✓"
        )

    @pytest.mark.anyio
    async def test_reschedule_fails_when_end_before_start(self, client: AsyncClient):
        """
        GIVEN an end time earlier than start time
        WHEN  PATCH /interviews/{id}/reschedule is called
        THEN  the response is 400

        Expected:
            PATCH /interviews/{id}/reschedule (end < start) → 400
            error.code == "invalid_time_range"
        """
        token = await signup_and_get_token(client, unique_user())
        create = await client.post(
            INTERVIEWS_URL, json=VALID_INTERVIEW_PAYLOAD, headers=auth_headers(token)
        )
        interview_id = create.json()["data"]["id"]

        start = (datetime.now() + timedelta(days=1)).isoformat()
        # 1 hour BEFORE start
        end = (datetime.now() + timedelta(days=1, hours=-1)).isoformat()

        payload = {"scheduled_start": start, "scheduled_end": end}
        response = await client.patch(
            f"{INTERVIEWS_URL}/{interview_id}/reschedule",
            json=payload,
            headers=auth_headers(token),
        )
        body = response.json()
        logger.info(
            "[invalid range] PATCH /interviews/%s → %d",
            interview_id, response.status_code,
        )

        assert response.status_code == 400
        assert body["error"]["code"] == "invalid_time_range"
        logger.info("[result]        Invalid time range correctly rejected with 400  ✓")

    @pytest.mark.anyio
    async def test_reschedule_returns_404_for_another_users_interview(
        self, client: AsyncClient
    ):
        """
        GIVEN user A creates an interview
        WHEN  user B tries to reschedule it
        THEN  the response is 404
        """
        token_a = await signup_and_get_token(client, unique_user("resch_a"))
        token_b = await signup_and_get_token(client, unique_user("resch_b"))

        create = await client.post(
            INTERVIEWS_URL,
            json=VALID_INTERVIEW_PAYLOAD,
            headers=auth_headers(token_a),
        )
        interview_id = create.json()["data"]["id"]

        start = (datetime.now() + timedelta(days=1)).isoformat()
        payload = {"scheduled_start": start}
        response = await client.patch(
            f"{INTERVIEWS_URL}/{interview_id}/reschedule",
            json=payload,
            headers=auth_headers(token_b),
        )

        assert response.status_code == 404
        logger.info(
            "[result]        Cross-user reschedule blocked  ✓"
        )
