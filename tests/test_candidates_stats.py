import time
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.main import app
from app.models.interview import Candidate, Interview
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember

STATS_URL = "/api/v1/candidates/stats"


def _seed_workspace(db_session, user_id, workspace_id, interview_count, distribution):
    """Seed a workspace with a user, membership, candidates, and interviews."""
    user = User(
        id=user_id,
        email=f"{uuid.uuid4().hex[:8]}@meetmind.ai",
        name="Test Recruiter",
        password_hash="mock_hash",
        is_verified=True,
    )
    workspace = Workspace(id=workspace_id, name="Test Company")
    membership = WorkspaceMember(workspace_id=workspace_id, user_id=user_id)

    candidate = Candidate(
        id=uuid.uuid4(), workspace_id=workspace_id, full_name="Candidate Pool"
    )

    interviews = [
        Interview(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            candidate_id=candidate.id,
            interviewer_id=user_id,
            status=distribution[i % len(distribution)],
        )
        for i in range(interview_count)
    ]

    db_session.add_all([user, workspace, membership, candidate] + interviews)
    return user


class TestCandidateStatsAccuracy:
    """Validate that aggregated counts match the seeded data."""

    @pytest.mark.anyio
    async def test_counts_match_seeded_data(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user_id = uuid.uuid4()
        workspace_id = uuid.uuid4()

        # 2 completed, 1 ongoing, 1 uncounted status
        distribution = ["completed", "completed", "ongoing", "failed"]
        user = _seed_workspace(db_session, user_id, workspace_id, 4, distribution)
        await db_session.commit()

        app.dependency_overrides[get_current_user] = lambda: user
        response = await client.get(
            STATS_URL, params={"workspace_id": str(workspace_id)}
        )
        app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 4
        assert data["completed"] == 2
        assert data["ongoing"] == 1
        assert data["needs_attention"] == 1

    @pytest.mark.anyio
    async def test_empty_workspace_returns_zeros(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user_id = uuid.uuid4()
        workspace_id = uuid.uuid4()

        user = User(
            id=user_id,
            email=f"{uuid.uuid4().hex[:8]}@meetmind.ai",
            name="Empty Workspace User",
            password_hash="mock_hash",
            is_verified=True,
        )
        workspace = Workspace(id=workspace_id, name="Empty Corp")
        membership = WorkspaceMember(workspace_id=workspace_id, user_id=user_id)

        db_session.add_all([user, workspace, membership])
        await db_session.commit()

        app.dependency_overrides[get_current_user] = lambda: user
        response = await client.get(
            STATS_URL, params={"workspace_id": str(workspace_id)}
        )
        app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total"] == 0
        assert data["completed"] == 0
        assert data["ongoing"] == 0
        assert data["needs_attention"] == 0


class TestCandidateStatsSecurity:
    """Validate that workspace access is enforced."""

    @pytest.mark.anyio
    async def test_non_member_receives_403(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user_id = uuid.uuid4()
        workspace_id = uuid.uuid4()

        user = User(
            id=user_id,
            email=f"{uuid.uuid4().hex[:8]}@meetmind.ai",
            name="Unauthorized User",
            password_hash="mock_hash",
            is_verified=True,
        )
        workspace = Workspace(id=workspace_id, name="Restricted Corp")

        db_session.add_all([user, workspace])
        await db_session.commit()

        app.dependency_overrides[get_current_user] = lambda: user
        response = await client.get(
            STATS_URL, params={"workspace_id": str(workspace_id)}
        )
        app.dependency_overrides.clear()

        assert response.status_code == 403
        body = response.json()
        assert body["success"] is False
        assert body["error"]["code"] == "forbidden"


class TestCandidateStatsPerformance:
    """Validate that SQL aggregation scales under production-grade load."""

    @pytest.mark.anyio
    async def test_aggregation_under_load(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        user_id = uuid.uuid4()
        workspace_id = uuid.uuid4()

        # Seed 1000 interviews with a realistic status spread
        distribution = (
            ["completed"] * 5 + ["ongoing"] * 2 + ["live"] + ["scheduled"] + ["failed"]
        )
        user = _seed_workspace(db_session, user_id, workspace_id, 1000, distribution)
        await db_session.commit()

        app.dependency_overrides[get_current_user] = lambda: user

        start = time.perf_counter()
        response = await client.get(
            STATS_URL, params={"workspace_id": str(workspace_id)}
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

        app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()["data"]

        assert data["total"] == 1000
        assert data["completed"] == 500
        assert data["ongoing"] == 300
        assert data["needs_attention"] == 100

        assert elapsed_ms < 500, f"Aggregation took {elapsed_ms:.0f}ms, expected <500ms"
