"""
Tests for Interview Scorecard Submission & Candidate Profile endpoints.

Endpoints under test
--------------------
PATCH /api/v1/interviews/{id}/scorecard  — submit or update scorecard
GET   /api/v1/interviews/{id}/profile    — retrieve aggregated candidate profile

Each test registers a unique user and creates its own interview so
sessions never collide across the shared in-memory SQLite database.

Run with:
    pytest tests/test_scorecard_and_profile.py -v -s
"""

from __future__ import annotations

import logging
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.interview import Interview
from app.models.scorecard import ScorecardCategory

logger = logging.getLogger(__name__)

# ── URL constants ──────────────────────────────────────────────────────────────

SIGNUP_URL = "/api/v1/auth/signup"
INTERVIEWS_URL = "/api/v1/interviews"

# ── Helpers ────────────────────────────────────────────────────────────────────


def unique_user(tag: str | None = None) -> dict:
    suffix = tag or uuid.uuid4().hex[:8]
    return {
        "name": "Score Tester",
        "email": f"scoretest_{suffix}@example.com",
        "password": "SecurePass1!",
    }


async def signup_and_get_token(client: AsyncClient, user: dict) -> str:
    response = await client.post(SIGNUP_URL, json=user)
    assert response.status_code == 201, (
        f"Signup failed: {response.status_code} — {response.json()}"
    )
    return response.json()["data"]["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


VALID_INTERVIEW_PAYLOAD = {
    "title": "Backend Engineer Interview",
    "candidate_name": "Ada Lovelace",
    "candidate_email": "ada@example.com",
    "job_description": "Build scalable APIs using FastAPI and PostgreSQL.",
    "scoring_rubric": "Communication, API design, problem-solving.",
    "role_title": "Senior Backend Engineer",
    "platform": "zoom",
    "ai_tone": "professional",
}


async def create_interview(client: AsyncClient, token: str) -> str:
    """Create an interview and return its ID."""
    response = await client.post(
        INTERVIEWS_URL,
        json=VALID_INTERVIEW_PAYLOAD,
        headers=auth_headers(token),
    )
    assert response.status_code == 201, f"Interview creation failed: {response.json()}"
    return response.json()["data"]["id"]


async def force_complete_interview(
    interview_id: str,
    db_session: AsyncSession,
) -> None:
    """
    Directly set interview status to 'completed' in the DB.

    The PATCH /scorecard endpoint requires a completed interview.
    There is no HTTP endpoint to transition status yet, so we
    write directly to the test DB.
    """
    db_session.expire_all()
    await db_session.execute(
        update(Interview)
        .where(Interview.id == uuid.UUID(interview_id))
        .values(status="completed")
    )
    await db_session.commit()


async def seed_category(
    workspace_id: str,
    db_session: AsyncSession,
    name: str = "Communication",
) -> str:
    """
    Insert a ScorecardCategory row and return its ID.

    Categories are workspace-scoped. The service validates that submitted
    category IDs belong to the interview's workspace, so we must seed
    a real category to test the happy path.
    """
    db_session.expire_all()
    category_id = uuid.uuid4()
    await db_session.execute(
        insert(ScorecardCategory).values(
            id=category_id,
            workspace_id=uuid.UUID(workspace_id),
            name=name,
        )
    )
    await db_session.commit()
    return str(category_id)


async def get_interview_workspace(
    interview_id: str,
    db_session: AsyncSession,
) -> str:
    db_session.expire_all()
    result = await db_session.execute(
        select(Interview.workspace_id).where(Interview.id == uuid.UUID(interview_id))
    )
    row = result.fetchone()
    assert row is not None, f"Interview {interview_id} not found in DB"
    return str(row[0])


# ── PATCH /interviews/{id}/scorecard ──────────────────────────────────────────


class TestSubmitScorecard:
    @pytest.mark.asyncio
    async def test_submit_new_scorecard_returns_200(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        GIVEN a completed interview with a valid workspace category
        WHEN  PATCH /interviews/{id}/scorecard is called with a valid payload
        THEN  the response is 200 with the persisted scorecard data

        Expected:
            PATCH /scorecard → 200
            data.overall_rating == 4
            data.scores[0].score_pct == 80
            data.scores[0].category_name == "Communication"
        """
        token = await signup_and_get_token(client, unique_user())
        interview_id = await create_interview(client, token)
        workspace_id = await get_interview_workspace(interview_id, db_session)

        await force_complete_interview(interview_id, db_session)
        category_id = await seed_category(workspace_id, db_session, "Communication")

        payload = {
            "overall_rating": 4,
            "scores": [{"category_id": category_id, "score_pct": 80}],
        }

        response = await client.patch(
            f"{INTERVIEWS_URL}/{interview_id}/scorecard",
            json=payload,
            headers=auth_headers(token),
        )
        body = response.json()
        logger.info(
            "[submit new] PATCH /scorecard → %d  body=%s",
            response.status_code,
            body,
        )

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}. Body: {body}"
        )
        data = body["data"]
        assert data["overall_rating"] == 4
        assert data["interview_id"] == interview_id
        assert len(data["scores"]) == 1
        assert data["scores"][0]["score_pct"] == 80
        assert data["scores"][0]["category_name"] == "Communication"
        assert "scorecard_id" in data
        assert "updated_at" in data
        logger.info("[result] New scorecard submitted and returned correctly.")

    @pytest.mark.asyncio
    async def test_update_existing_scorecard_returns_200(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        GIVEN a scorecard was already submitted for a completed interview
        WHEN  PATCH /interviews/{id}/scorecard is called again with new values
        THEN  the response is 200 with the updated score — no duplicate
              scorecard created

        Expected:
            First  PATCH → 200  score_pct=60
            Second PATCH → 200  score_pct=90  (updated)
            Only one scorecard row exists for the interview
        """
        token = await signup_and_get_token(client, unique_user())
        interview_id = await create_interview(client, token)
        workspace_id = await get_interview_workspace(interview_id, db_session)

        await force_complete_interview(interview_id, db_session)
        category_id = await seed_category(workspace_id, db_session, "Problem Solving")

        payload_v1 = {
            "overall_rating": 3,
            "scores": [{"category_id": category_id, "score_pct": 60}],
        }
        r1 = await client.patch(
            f"{INTERVIEWS_URL}/{interview_id}/scorecard",
            json=payload_v1,
            headers=auth_headers(token),
        )
        assert r1.status_code == 200, f"First submit failed: {r1.json()}"
        scorecard_id_first = r1.json()["data"]["scorecard_id"]
        logger.info("[first submit] scorecard_id=%s.", scorecard_id_first)

        payload_v2 = {
            "overall_rating": 5,
            "scores": [{"category_id": category_id, "score_pct": 90}],
        }
        r2 = await client.patch(
            f"{INTERVIEWS_URL}/{interview_id}/scorecard",
            json=payload_v2,
            headers=auth_headers(token),
        )
        body = r2.json()
        logger.info(
            "[update] PATCH /scorecard → %d  body=%s",
            r2.status_code,
            body,
        )

        assert r2.status_code == 200, (
            f"Expected 200 on update, got {r2.status_code}. Body: {body}"
        )
        data = body["data"]

        # Same scorecard_id — upsert, not insert
        assert data["scorecard_id"] == scorecard_id_first, (
            "Expected the same scorecard_id on update (upsert), "
            f"got a new one: {data['scorecard_id']}"
        )
        assert data["overall_rating"] == 5
        assert data["scores"][0]["score_pct"] == 90
        logger.info("[result] Scorecard updated correctly, no duplicate created.")

    @pytest.mark.asyncio
    async def test_submit_returns_422_when_interview_not_completed(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        GIVEN an interview in 'draft' status
        WHEN  PATCH /interviews/{id}/scorecard is called
        THEN  the response is 422 with code 'interview_not_completed'

        Expected:
            PATCH /scorecard (draft interview) → 422
            error.code == "interview_not_completed"
        """
        token = await signup_and_get_token(client, unique_user())
        interview_id = await create_interview(client, token)
        workspace_id = await get_interview_workspace(interview_id, db_session)
        category_id = await seed_category(workspace_id, db_session)

        payload = {
            "overall_rating": 3,
            "scores": [{"category_id": category_id, "score_pct": 70}],
        }
        response = await client.patch(
            f"{INTERVIEWS_URL}/{interview_id}/scorecard",
            json=payload,
            headers=auth_headers(token),
        )
        body = response.json()
        logger.info(
            "[not completed] PATCH /scorecard → %d  body=%s",
            response.status_code,
            body,
        )

        assert response.status_code == 422, (
            f"Expected 422 for non-completed interview, got "
            f"{response.status_code}. Body: {body}"
        )
        assert body["error"]["code"] == "interview_not_completed"
        logger.info("[result] Non-completed interview correctly rejected.")

    @pytest.mark.asyncio
    async def test_submit_returns_422_for_invalid_category(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        GIVEN a completed interview
        WHEN  PATCH /scorecard is called with a category_id not in the workspace
        THEN  the response is 422 with code 'invalid_scorecard_category'

        Expected:
            PATCH /scorecard (bad category_id) → 422
            error.code == "invalid_scorecard_category"
        """
        token = await signup_and_get_token(client, unique_user())
        interview_id = await create_interview(client, token)
        await force_complete_interview(interview_id, db_session)

        # Use a random UUID — not seeded, not in this workspace
        fake_category_id = str(uuid.uuid4())
        payload = {
            "overall_rating": 3,
            "scores": [{"category_id": fake_category_id, "score_pct": 50}],
        }
        response = await client.patch(
            f"{INTERVIEWS_URL}/{interview_id}/scorecard",
            json=payload,
            headers=auth_headers(token),
        )
        body = response.json()
        logger.info(
            "[bad category] PATCH /scorecard → %d  body=%s",
            response.status_code,
            body,
        )

        assert response.status_code == 422, (
            f"Expected 422 for invalid category, got "
            f"{response.status_code}. Body: {body}"
        )
        assert body["error"]["code"] == "invalid_scorecard_category"
        logger.info("[result] Invalid category correctly rejected.")

    @pytest.mark.asyncio
    async def test_submit_returns_404_for_another_users_interview(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        GIVEN user A creates a completed interview
        WHEN  user B calls PATCH /scorecard on it
        THEN  the response is 404 — cross-user access blocked

        Expected:
            PATCH /scorecard (user B on user A's interview) → 404
        """
        token_a = await signup_and_get_token(client, unique_user("sc_a"))
        token_b = await signup_and_get_token(client, unique_user("sc_b"))

        interview_id = await create_interview(client, token_a)
        workspace_id = await get_interview_workspace(interview_id, db_session)
        await force_complete_interview(interview_id, db_session)
        category_id = await seed_category(workspace_id, db_session)

        payload = {
            "overall_rating": 3,
            "scores": [{"category_id": category_id, "score_pct": 60}],
        }
        response = await client.patch(
            f"{INTERVIEWS_URL}/{interview_id}/scorecard",
            json=payload,
            headers=auth_headers(token_b),
        )
        body = response.json()
        logger.info("[cross user] PATCH /scorecard → %d", response.status_code)

        assert response.status_code == 404, (
            f"Expected 404 for cross-user access, got "
            f"{response.status_code}. Body: {body}"
        )
        logger.info("[result] Cross-user scorecard access correctly blocked.")

    @pytest.mark.asyncio
    async def test_submit_returns_401_without_token(self, client: AsyncClient):
        """
        GIVEN no Authorization header
        WHEN  PATCH /scorecard is called
        THEN  the response is 401

        Expected:
            PATCH /scorecard (no auth) → 401
        """
        fake_id = str(uuid.uuid4())
        payload = {
            "overall_rating": 3,
            "scores": [{"category_id": str(uuid.uuid4()), "score_pct": 50}],
        }
        response = await client.patch(
            f"{INTERVIEWS_URL}/{fake_id}/scorecard",
            json=payload,
        )
        logger.info("[no auth] PATCH /scorecard → %d", response.status_code)

        assert response.status_code == 401
        logger.info("[result] Unauthenticated scorecard request correctly rejected.")


# ── GET /interviews/{id}/profile ──────────────────────────────────────────────


class TestGetCandidateProfile:
    @pytest.mark.asyncio
    async def test_profile_returns_candidate_and_interview_data(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        GIVEN a created interview with no scorecard or summary yet
        WHEN  GET /interviews/{id}/profile is called
        THEN  the response is 200 with candidate and interview data,
              scorecard and summary as null

        Expected:
            GET /profile → 200
            data.candidate.full_name == "Ada Lovelace"
            data.scorecard == null
            data.summary   == null
            data.transcript_status == null
        """
        token = await signup_and_get_token(client, unique_user())
        interview_id = await create_interview(client, token)

        response = await client.get(
            f"{INTERVIEWS_URL}/{interview_id}/profile",
            headers=auth_headers(token),
        )
        body = response.json()
        logger.info(
            "[profile basic] GET /profile → %d  body=%s",
            response.status_code,
            body,
        )

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}. Body: {body}"
        )
        data = body["data"]
        assert data["candidate"]["full_name"] == "Ada Lovelace"
        assert data["candidate"]["email"] == "ada@example.com"
        assert data["interview"]["id"] == interview_id
        assert data["interview"]["status"] == "draft"
        assert data["scorecard"] is None
        assert data["summary"] is not None
        assert data["summary"]["ai_assessment"] is None
        assert data["summary"]["skills_to_assess"] == []
        assert data["summary"]["highlights"] == []
        assert data["summary"]["red_flags"] == []
        assert data["transcript_status"] is None
        logger.info("[result] Profile returned with nulls for missing data.")

    @pytest.mark.asyncio
    async def test_profile_includes_scorecard_after_submission(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        GIVEN a completed interview with a submitted scorecard
        WHEN  GET /interviews/{id}/profile is called
        THEN  the scorecard is populated in the profile response

        Expected:
            PATCH /scorecard → 200
            GET   /profile   → 200  data.scorecard is not null
            data.scorecard.overall_rating == 4
        """
        token = await signup_and_get_token(client, unique_user())
        interview_id = await create_interview(client, token)
        workspace_id = await get_interview_workspace(interview_id, db_session)

        await force_complete_interview(interview_id, db_session)
        category_id = await seed_category(workspace_id, db_session, "API Design")

        patch_response = await client.patch(
            f"{INTERVIEWS_URL}/{interview_id}/scorecard",
            json={
                "overall_rating": 4,
                "scores": [{"category_id": category_id, "score_pct": 75}],
            },
            headers=auth_headers(token),
        )
        assert patch_response.status_code == 200, (
            f"Scorecard submission failed: {patch_response.json()}"
        )
        logger.info("[setup] Scorecard submitted")

        response = await client.get(
            f"{INTERVIEWS_URL}/{interview_id}/profile",
            headers=auth_headers(token),
        )
        body = response.json()
        logger.info(
            "[profile with scorecard] GET /profile → %d",
            response.status_code,
        )

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}. Body: {body}"
        )
        data = body["data"]
        assert data["scorecard"] is not None, "Expected scorecard to be populated"
        assert data["scorecard"]["overall_rating"] == 4
        assert len(data["scorecard"]["scores"]) == 1
        assert data["scorecard"]["scores"][0]["score_pct"] == 75
        assert data["scorecard"]["scores"][0]["category_name"] == "API Design"
        logger.info("[result] Profile correctly includes submitted scorecard")

    @pytest.mark.asyncio
    async def test_profile_returns_404_for_nonexistent_interview(
        self, client: AsyncClient
    ):
        """
        GIVEN a random UUID that does not exist
        WHEN  GET /interviews/{id}/profile is called
        THEN  the response is 404

        Expected:
            GET /profile (fake id) → 404
            error.code == "interview_not_found"
        """
        token = await signup_and_get_token(client, unique_user())
        fake_id = str(uuid.uuid4())

        response = await client.get(
            f"{INTERVIEWS_URL}/{fake_id}/profile",
            headers=auth_headers(token),
        )
        body = response.json()
        logger.info("[not found] GET /profile/%s → %d", fake_id, response.status_code)

        assert response.status_code == 404, (
            f"Expected 404, got {response.status_code}. Body: {body}"
        )
        assert body["error"]["code"] == "interview_not_found"
        logger.info("[result] Nonexistent interview correctly returns 404")

    @pytest.mark.asyncio
    async def test_profile_returns_404_for_another_users_interview(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        GIVEN user A creates an interview
        WHEN  user B calls GET /profile on it
        THEN  the response is 404

        Expected:
            GET /profile (user B on user A's interview) → 404
        """
        token_a = await signup_and_get_token(client, unique_user("prof_a"))
        token_b = await signup_and_get_token(client, unique_user("prof_b"))

        interview_id = await create_interview(client, token_a)

        response = await client.get(
            f"{INTERVIEWS_URL}/{interview_id}/profile",
            headers=auth_headers(token_b),
        )
        body = response.json()
        logger.info("[cross user] GET /profile → %d", response.status_code)

        assert response.status_code == 404, (
            f"Expected 404 for cross-user profile access, got "
            f"{response.status_code}. Body: {body}"
        )
        logger.info("[result] Cross-user profile access correctly blocked")

    @pytest.mark.asyncio
    async def test_profile_returns_401_without_token(self, client: AsyncClient):
        """
        GIVEN no Authorization header
        WHEN  GET /profile is called
        THEN  the response is 401

        Expected:
            GET /profile (no auth) → 401
        """
        fake_id = str(uuid.uuid4())
        response = await client.get(f"{INTERVIEWS_URL}/{fake_id}/profile")
        logger.info("[no auth] GET /profile → %d", response.status_code)

        assert response.status_code == 401
        logger.info("[result] Unauthenticated profile request correctly rejected")
