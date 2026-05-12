from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class DashboardSchedule(BaseModel):
    id: UUID
    candidate_name: str
    role_title: str | None
    scheduled_start: datetime | None
    platform: str | None


class DashboardCompleted(BaseModel):
    id: UUID
    candidate_name: str
    score: float
    completed_at: datetime | None
    status: str
