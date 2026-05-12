import uuid
from datetime import date, datetime, time
from typing import List, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.interview import Candidate, Interview


async def get_calendar_appointments(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    filter_date: Optional[date] = None,
) -> List[dict]:
    """Retrieve scheduled interview appointments for a specific workspace.

    This service performs a relational join between Interviews and Candidates
    to return a comprehensive view of upcoming engagements.

    Args:
        db: The asynchronous database session.
        workspace_id: The unique identifier of the workspace.
        filter_date: Optional date to filter appointments. If omitted,
            returns all future appointments from the current timestamp.

    Returns:
        A list of dictionaries containing appointment details:
        - id: Interview UUID
        - scheduled_start: Start timestamp
        - scheduled_end: End timestamp
        - role_title: The position being interviewed for
        - status: Current interview status
        - candidate_name: Full name of the candidate
        - candidate_email: Contact email of the candidate
    """
    stmt = (
        select(
            Interview.id,
            Interview.scheduled_start,
            Interview.scheduled_end,
            Interview.role_title,
            Interview.status,
            Candidate.full_name.label("candidate_name"),
            Candidate.email.label("candidate_email"),
        )
        .join(Candidate, Interview.candidate_id == Candidate.id)
        .where(Interview.workspace_id == workspace_id)
    )

    if filter_date:
        # Define the temporal boundary for the requested date
        start_dt = datetime.combine(filter_date, time.min)
        end_dt = datetime.combine(filter_date, time.max)
        stmt = stmt.where(
            and_(
                Interview.scheduled_start >= start_dt,
                Interview.scheduled_start <= end_dt,
            )
        )
    else:
        # Default to showing all upcoming appointments to ensure recruiter visibility
        stmt = stmt.where(Interview.scheduled_start >= datetime.now())

    # Sort chronologically to provide a natural calendar flow
    stmt = stmt.order_by(Interview.scheduled_start.asc())

    result = await db.execute(stmt)
    rows = result.all()

    return [dict(row._mapping) for row in rows]
