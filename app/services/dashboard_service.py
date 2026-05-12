from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.interview import Interview


class DashboardService:
    @staticmethod
    async def get_upcoming_schedule(db: AsyncSession, interviewer_id: UUID):
        query = (
            select(Interview)
            .options(joinedload(Interview.candidate))
            .where(Interview.interviewer_id == interviewer_id)
            .where(Interview.status == "scheduled")
            .where(Interview.scheduled_start >= datetime.utcnow())
            .order_by(Interview.scheduled_start.asc())
        )
        result = await db.execute(query)
        return result.scalars().all()

    @staticmethod
    async def get_completed_interviews(db: AsyncSession, interviewer_id: UUID):
        query = (
            select(Interview)
            .options(joinedload(Interview.candidate))
            .where(Interview.interviewer_id == interviewer_id)
            .where(Interview.status == "completed")
            .order_by(Interview.scheduled_end.desc())
            .limit(5)
        )
        result = await db.execute(query)
        return result.scalars().all()
