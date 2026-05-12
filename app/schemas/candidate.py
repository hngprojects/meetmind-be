"""Candidate response schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class InterviewHighlightOut(BaseModel):
    content: str
    sort_order: int | None = None


class InterviewRedFlagOut(BaseModel):
    content: str
    sort_order: int | None = None


class InterviewSkillOut(BaseModel):
    skill: str
    sort_order: int | None = None


class InterviewSummaryOut(BaseModel):
    ai_assessment: str | None = None
    status: str | None = None
    highlights: list[InterviewHighlightOut] = []
    red_flags: list[InterviewRedFlagOut] = []
    skills_assessed: list[InterviewSkillOut] = []


class InterviewOut(BaseModel):
    id: UUID
    role_title: str | None = None
    status: str | None = None
    platform: str | None = None
    scheduled_start: datetime | None = None
    duration_min: int | None = None
    rating: int | None = None
    questions_asked: int | None = None
    questions_total: int | None = None
    summary: InterviewSummaryOut | None = None


class CandidateStatsOut(BaseModel):
    total_interviews: int
    completed: int
    scheduled: int
    average_rating: float | None = None


class CandidateProfileOut(BaseModel):
    id: UUID
    full_name: str
    email: str | None = None
    phone: str | None = None
    avatar_initials: str | None = None
    resume_url: str | None = None
    portfolio_url: str | None = None
    stats: CandidateStatsOut
    interviews: list[InterviewOut] = []
