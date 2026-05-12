"""
Tests for the Candidate Profile endpoint.

Endpoints under test
--------------------
GET /api/v1/candidates/{candidate_id}  — retrieve full candidate profile


Each test registers a unique user so sessions never collide across the
shared in-memory SQLite database.

Run with:
    pytest tests/test_candidates.py -v -s
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.interview import (
    Candidate,
    Interview,
    InterviewHighlight,
    InterviewRedFlag,
    InterviewSkillToAssess,
    InterviewSummary,
)
from app.models.workspace import Workspace

logger = logging.getLogger(__name__)

# ── URL constants ──────────────────────────────────────────────────────────────

SIGNUP_URL = "/api/v1/auth/signup"
CANDIDATES_URL = "/api/v1/candidates"

# ── helpers ────────────────────────────────────────────────────────────────────


def unique_user(tag: str | None = None) -> dict:
    """Return a signup payload with a guaranteed-unique email."""
    suffix = tag or uuid.uuid4().hex[:8]
    return {
        "name": "Candidate Tester",
        "email": f"candidate_{suffix}@example.com",
        "password": "SecurePass1!",
    }


async def signup_and_get_token(client: AsyncClient, user: dict) -> tuple[str, str]:
    """Register a user and return (access_token, user_id)."""
    response = await client.post(SIGNUP_URL, json=user)
    assert response.status_code == 201, (
        f"Signup failed: {response.status_code} — {response.json()}"
    )
    data = response.json()["data"]
    return data["access_token"], data["id"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── GET /candidates/{candidate_id} ─────────────────────────────────────────────


class TestGetCandidate:
    @pytest.mark.anyio
    async def test_returns_candidate_profile(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        GIVEN a candidate exists in the database with all optional fields filled
        WHEN  GET /candidates/{id} is called
        THEN  the response is 200 with the full candidate profile, empty stats
        """
        token, _ = await signup_and_get_token(client, unique_user())

        ws = Workspace(name="Test Workspace")
        db_session.add(ws)
        await db_session.commit()
        await db_session.refresh(ws)

        candidate = Candidate(
            workspace_id=ws.id,
            full_name="Jane Doe",
            email="jane@example.com",
            phone="+1234567890",
            avatar_initials="JD",
            resume_url="https://example.com/resume.pdf",
            portfolio_url="https://example.com/portfolio",
        )
        db_session.add(candidate)
        await db_session.commit()
        await db_session.refresh(candidate)
        logger.info("[seed] Created candidate %s", candidate.id)

        response = await client.get(
            f"{CANDIDATES_URL}/{candidate.id}",
            headers=auth_headers(token),
        )
        body = response.json()
        logger.info("[get] GET /candidates/%s → %d", candidate.id, response.status_code)

        assert response.status_code == 200, (
            f"Expected 200 but got {response.status_code}. Body: {body}"
        )
        assert body["id"] == str(candidate.id)
        assert body["full_name"] == "Jane Doe"
        assert body["email"] == "jane@example.com"
        assert body["phone"] == "+1234567890"
        assert body["avatar_initials"] == "JD"
        assert body["resume_url"] == "https://example.com/resume.pdf"
        assert body["portfolio_url"] == "https://example.com/portfolio"
        assert body["stats"]["total_interviews"] == 0
        assert body["stats"]["completed"] == 0
        assert body["stats"]["scheduled"] == 0
        assert body["stats"]["average_rating"] is None
        assert body["interviews"] == []
        logger.info("[result] Candidate profile returned with correct fields  ✓")

    @pytest.mark.anyio
    async def test_returns_401_without_token(self, client: AsyncClient):
        """
        GIVEN no Authorization header
        WHEN  GET /candidates/{id} is called
        THEN  the response is 401
        """
        fake_id = str(uuid.uuid4())
        response = await client.get(f"{CANDIDATES_URL}/{fake_id}")
        logger.info("[no auth] GET /candidates/%s → %d", fake_id, response.status_code)

        assert response.status_code == 401, (
            f"Expected 401 but got {response.status_code}. Body: {response.json()}"
        )
        logger.info("[result]  Unauthenticated request correctly rejected  ✓")

    @pytest.mark.anyio
    async def test_returns_404_for_nonexistent_candidate(self, client: AsyncClient):
        """
        GIVEN a random UUID that does not exist in the database
        WHEN  GET /candidates/{id} is called
        THEN  the response is 404
        """
        token, _ = await signup_and_get_token(client, unique_user())
        fake_id = str(uuid.uuid4())
        response = await client.get(
            f"{CANDIDATES_URL}/{fake_id}",
            headers=auth_headers(token),
        )
        body = response.json()
        logger.info(
            "[not found] GET /candidates/%s → %d", fake_id, response.status_code
        )

        assert response.status_code == 404, (
            f"Expected 404 but got {response.status_code}. Body: {body}"
        )
        logger.info("[result]  Nonexistent candidate correctly returns 404  ✓")

    @pytest.mark.anyio
    async def test_stats_and_interviews_returned(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        GIVEN a candidate with multiple interviews of varying statuses and ratings
        WHEN  GET /candidates/{id} is called
        THEN  the response includes all interviews and correctly computed stats

        Expected:
            total_interviews == 3
            completed        == 2
            scheduled        == 1
            average_rating   == 4.5  (ratings: 4 + 5 = 9, 9 / 2 = 4.5)
        """
        token, user_id = await signup_and_get_token(client, unique_user())

        ws = Workspace(name="Test Workspace")
        db_session.add(ws)
        await db_session.commit()
        await db_session.refresh(ws)

        candidate = Candidate(workspace_id=ws.id, full_name="John Smith")
        db_session.add(candidate)
        await db_session.commit()
        await db_session.refresh(candidate)
        logger.info("[seed] Created candidate %s", candidate.id)

        base_time = datetime(2025, 6, 1, 10, 0, 0)
        interviewer_id = uuid.UUID(user_id)

        int1 = Interview(
            workspace_id=ws.id,
            candidate_id=candidate.id,
            interviewer_id=interviewer_id,
            role_title="Backend Engineer",
            status="completed",
            scheduled_start=base_time,
            duration_min=60,
            platform="zoom",
            rating=4,
            questions_asked=8,
            questions_total=10,
        )
        int2 = Interview(
            workspace_id=ws.id,
            candidate_id=candidate.id,
            interviewer_id=interviewer_id,
            role_title="Frontend Engineer",
            status="completed",
            scheduled_start=base_time,
            duration_min=45,
            platform="google_meet",
            rating=5,
            questions_asked=6,
            questions_total=6,
        )
        int3 = Interview(
            workspace_id=ws.id,
            candidate_id=candidate.id,
            interviewer_id=interviewer_id,
            role_title="DevOps Engineer",
            status="scheduled",
            scheduled_start=base_time,
            duration_min=30,
            platform="teams",
        )
        db_session.add_all([int1, int2, int3])
        await db_session.commit()
        await db_session.refresh(int1)
        await db_session.refresh(int2)
        await db_session.refresh(int3)
        logger.info("[seed] Created 3 interviews for candidate")

        response = await client.get(
            f"{CANDIDATES_URL}/{candidate.id}",
            headers=auth_headers(token),
        )
        body = response.json()
        logger.info("[get] GET /candidates/%s → %d", candidate.id, response.status_code)

        assert response.status_code == 200
        assert body["stats"]["total_interviews"] == 3
        assert body["stats"]["completed"] == 2
        assert body["stats"]["scheduled"] == 1
        assert body["stats"]["average_rating"] == 4.5

        assert len(body["interviews"]) == 3
        role_titles = {i["role_title"] for i in body["interviews"]}
        assert role_titles == {
            "Backend Engineer",
            "Frontend Engineer",
            "DevOps Engineer",
        }
        logger.info("[result] Stats and interview list correct  ✓")

    @pytest.mark.anyio
    async def test_summary_nested_data(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        GIVEN a candidate with an interview that has a full summary
          (highlights, red flags, skills_assessed)
        WHEN  GET /candidates/{id} is called
        THEN  the response includes the nested summary data
        """
        token, user_id = await signup_and_get_token(client, unique_user())

        ws = Workspace(name="Test Workspace")
        db_session.add(ws)
        await db_session.commit()
        await db_session.refresh(ws)

        candidate = Candidate(workspace_id=ws.id, full_name="Summary Test")
        db_session.add(candidate)
        await db_session.commit()
        await db_session.refresh(candidate)

        interview = Interview(
            workspace_id=ws.id,
            candidate_id=candidate.id,
            interviewer_id=uuid.UUID(user_id),
            role_title="Engineer",
            status="completed",
        )
        db_session.add(interview)
        await db_session.commit()
        await db_session.refresh(interview)

        summary = InterviewSummary(
            interview_id=interview.id,
            ai_assessment="Strong technical skills",
            status="generated",
        )
        db_session.add(summary)
        await db_session.commit()
        await db_session.refresh(summary)
        logger.info("[seed] Created summary %s", summary.id)

        highlights = [
            InterviewHighlight(
                summary_id=summary.id,
                content="Great problem solver",
                sort_order=1,
            ),
            InterviewHighlight(
                summary_id=summary.id,
                content="Clear communicator",
                sort_order=2,
            ),
        ]
        red_flags = [
            InterviewRedFlag(
                summary_id=summary.id,
                content="Needs more system design practice",
                sort_order=1,
            ),
        ]
        skills = [
            InterviewSkillToAssess(summary_id=summary.id, skill="Python", sort_order=1),
            InterviewSkillToAssess(
                summary_id=summary.id, skill="FastAPI", sort_order=2
            ),
            InterviewSkillToAssess(
                summary_id=summary.id, skill="PostgreSQL", sort_order=3
            ),
        ]
        db_session.add_all(highlights + red_flags + skills)
        await db_session.commit()
        logger.info("[seed] Created highlights, red flags, and skills")

        response = await client.get(
            f"{CANDIDATES_URL}/{candidate.id}",
            headers=auth_headers(token),
        )
        body = response.json()
        logger.info("[get] GET /candidates/%s → %d", candidate.id, response.status_code)

        assert response.status_code == 200
        assert len(body["interviews"]) == 1

        interview_data = body["interviews"][0]
        assert interview_data["summary"] is not None
        assert interview_data["summary"]["ai_assessment"] == "Strong technical skills"
        assert interview_data["summary"]["status"] == "generated"
        assert len(interview_data["summary"]["highlights"]) == 2
        hl0 = interview_data["summary"]["highlights"][0]
        hl1 = interview_data["summary"]["highlights"][1]
        assert hl0["content"] == "Great problem solver"
        assert hl0["sort_order"] == 1
        assert hl1["content"] == "Clear communicator"

        assert len(interview_data["summary"]["red_flags"]) == 1
        rf0 = interview_data["summary"]["red_flags"][0]
        assert rf0["content"] == "Needs more system design practice"
        assert len(interview_data["summary"]["skills_assessed"]) == 3
        assert interview_data["summary"]["skills_assessed"][0]["skill"] == "Python"
        assert interview_data["summary"]["skills_assessed"][1]["skill"] == "FastAPI"
        assert interview_data["summary"]["skills_assessed"][2]["skill"] == "PostgreSQL"
        logger.info("[result] Nested summary data returned correctly  ✓")

    @pytest.mark.anyio
    async def test_interview_without_summary(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        GIVEN a candidate with an interview that has NO summary
        WHEN  GET /candidates/{id} is called
        THEN  the interview's summary field is null
        """
        token, user_id = await signup_and_get_token(client, unique_user())

        ws = Workspace(name="Test Workspace")
        db_session.add(ws)
        await db_session.commit()
        await db_session.refresh(ws)

        candidate = Candidate(workspace_id=ws.id, full_name="No Summary")
        db_session.add(candidate)
        await db_session.commit()
        await db_session.refresh(candidate)

        interview = Interview(
            workspace_id=ws.id,
            candidate_id=candidate.id,
            interviewer_id=uuid.UUID(user_id),
            role_title="Engineer",
            status="scheduled",
        )
        db_session.add(interview)
        await db_session.commit()

        response = await client.get(
            f"{CANDIDATES_URL}/{candidate.id}",
            headers=auth_headers(token),
        )
        body = response.json()

        assert response.status_code == 200
        assert len(body["interviews"]) == 1
        assert body["interviews"][0]["summary"] is None
        logger.info("[result] Interview without summary correctly yields null  ✓")

    @pytest.mark.anyio
    async def test_average_rating_is_none_when_no_completed_interviews(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        GIVEN a candidate with only scheduled (unrated) interviews
        WHEN  GET /candidates/{id} is called
        THEN  average_rating is None instead of 0.0
        """
        token, user_id = await signup_and_get_token(client, unique_user("rating_none"))

        ws = Workspace(name="Test Workspace")
        db_session.add(ws)
        await db_session.commit()
        await db_session.refresh(ws)

        candidate = Candidate(workspace_id=ws.id, full_name="No Ratings")
        db_session.add(candidate)
        await db_session.commit()
        await db_session.refresh(candidate)

        interview = Interview(
            workspace_id=ws.id,
            candidate_id=candidate.id,
            interviewer_id=uuid.UUID(user_id),
            role_title="Engineer",
            status="scheduled",
        )
        db_session.add(interview)
        await db_session.commit()

        response = await client.get(
            f"{CANDIDATES_URL}/{candidate.id}",
            headers=auth_headers(token),
        )
        body = response.json()

        assert response.status_code == 200
        assert body["stats"]["average_rating"] is None
        logger.info("[result] average_rating is None when no completed interviews  ✓")

    @pytest.mark.anyio
    async def test_interviews_ordered_by_scheduled_start_desc(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        GIVEN a candidate with multiple interviews on different dates
        WHEN  GET /candidates/{id} is called
        THEN  interviews are sorted by scheduled_start descending
        """
        token, user_id = await signup_and_get_token(client, unique_user("ordering"))

        ws = Workspace(name="Test Workspace")
        db_session.add(ws)
        await db_session.commit()
        await db_session.refresh(ws)

        candidate = Candidate(workspace_id=ws.id, full_name="Order Test")
        db_session.add(candidate)
        await db_session.commit()
        await db_session.refresh(candidate)

        interviewer_id = uuid.UUID(user_id)

        past = Interview(
            workspace_id=ws.id,
            candidate_id=candidate.id,
            interviewer_id=interviewer_id,
            role_title="Past",
            status="completed",
            scheduled_start=datetime(2025, 1, 1),
        )
        recent = Interview(
            workspace_id=ws.id,
            candidate_id=candidate.id,
            interviewer_id=interviewer_id,
            role_title="Recent",
            status="completed",
            scheduled_start=datetime(2025, 6, 15),
        )
        middle = Interview(
            workspace_id=ws.id,
            candidate_id=candidate.id,
            interviewer_id=interviewer_id,
            role_title="Middle",
            status="completed",
            scheduled_start=datetime(2025, 3, 1),
        )
        db_session.add_all([past, recent, middle])
        await db_session.commit()

        response = await client.get(
            f"{CANDIDATES_URL}/{candidate.id}",
            headers=auth_headers(token),
        )
        body = response.json()

        assert response.status_code == 200
        titles = [i["role_title"] for i in body["interviews"]]
        assert titles == ["Recent", "Middle", "Past"], (
            f"Expected [Recent, Middle, Past] but got {titles}"
        )
        logger.info("[result] Interviews ordered by scheduled_start desc  ✓")
