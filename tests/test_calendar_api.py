import uuid
from datetime import date, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.main import app
from app.models.interview import Candidate, Interview
from app.models.user import User
from app.models.workspace import WorkspaceMember


@pytest.fixture
async def calendar_setup(db_session: AsyncSession):
    user_id = uuid.uuid4()
    workspace_id = uuid.uuid4()

    user = User(
        id=user_id,
        email=f"cal-{uuid.uuid4().hex[:8]}@meetmind.ai",
        name="Calendar Tester",
    )
    db_session.add(user)

    member = WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role="admin")
    db_session.add(member)

    candidate = Candidate(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        full_name="Jane Doe",
        email="jane@example.com",
    )
    db_session.add(candidate)

    # Reference time to avoid race conditions
    now = datetime.now()

    # Today's interview (1 hour from now)
    interview_today = Interview(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        candidate_id=candidate.id,
        interviewer_id=user_id,
        scheduled_start=now + timedelta(hours=1),
        scheduled_end=now + timedelta(hours=2),
        status="scheduled",
        role_title="Software Engineer",
    )
    db_session.add(interview_today)

    # Tomorrow's interview
    interview_tomorrow = Interview(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        candidate_id=candidate.id,
        interviewer_id=user_id,
        scheduled_start=now + timedelta(days=1),
        scheduled_end=now + timedelta(days=1, hours=1),
        status="scheduled",
        role_title="Product Manager",
    )
    db_session.add(interview_tomorrow)

    await db_session.commit()
    return user, workspace_id


@pytest.mark.anyio
async def test_list_calendar_today(client: AsyncClient, calendar_setup):
    user, workspace_id = calendar_setup
    app.dependency_overrides[get_current_user] = lambda: user

    today_str = date.today().isoformat()
    response = await client.get(
        "/api/v1/calendar",
        params={"workspace_id": str(workspace_id), "date": today_str},
    )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["appointments"]) == 1
    assert data["appointments"][0]["role_title"] == "Software Engineer"
    assert data["appointments"][0]["candidate_name"] == "Jane Doe"


@pytest.mark.anyio
async def test_list_calendar_unauthorized(client: AsyncClient, calendar_setup):
    user, _ = calendar_setup
    other_workspace_id = uuid.uuid4()
    app.dependency_overrides[get_current_user] = lambda: user

    response = await client.get(
        "/api/v1/calendar", params={"workspace_id": str(other_workspace_id)}
    )

    app.dependency_overrides.clear()

    assert response.status_code == 403


@pytest.mark.anyio
async def test_list_calendar_default_returns_all_future(
    client: AsyncClient, calendar_setup
):
    """Verify that without a date parameter, all future appointments are returned."""
    user, workspace_id = calendar_setup
    app.dependency_overrides[get_current_user] = lambda: user

    response = await client.get(
        "/api/v1/calendar", params={"workspace_id": str(workspace_id)}
    )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()["data"]
    # The setup seeds one today and one tomorrow, both should be returned
    assert len(data["appointments"]) >= 2
