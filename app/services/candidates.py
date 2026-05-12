import uuid
from typing import Any, Dict

from sqlalchemy import case, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.interview import Interview


async def get_candidate_stats(
    db: AsyncSession, workspace_id: uuid.UUID
) -> Dict[str, Any]:
    """Fetch aggregated candidate statistics for a specific workspace.

    Aggregates counts for total, completed, and ongoing interviews
    at the database level to optimize performance.
    """
    stmt = select(
        func.count(Interview.id).label("total"),
        func.sum(case((Interview.status == "completed", 1), else_=0)).label("completed"),
        func.sum(case((Interview.status.in_(["ongoing", "live"]), 1), else_=0)).label("ongoing"),
        func.sum(case((Interview.status == "failed", 1), else_=0)).label("needs_attention"),
    ).where(Interview.workspace_id == workspace_id)

    result = await db.execute(stmt)
    row = result.first()

    return {
        "total": int(row.total or 0) if row else 0,
        "completed": int(row.completed or 0) if row else 0,
        "ongoing": int(row.ongoing or 0) if row else 0,
        "needs_attention": int(row.needs_attention or 0) if row else 0,
    }
