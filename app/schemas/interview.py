from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field

# ── Request schemas ────────────────────────────────────────────────────────────


class CreateInterviewRequest(BaseModel):
    """Payload for creating a new interview session."""

    title: str = Field(..., min_length=1, max_length=200)
    candidate_name: str = Field(..., min_length=1, max_length=120)
    candidate_email: str | None = Field(default=None)
    job_description: str = Field(..., min_length=1)
    scoring_rubric: str = Field(..., min_length=1)
    role_title: str | None = Field(default=None, max_length=120)
    platform: str | None = Field(default=None, max_length=30)
    ai_tone: str | None = Field(default=None, max_length=20)


# ── Response schemas ───────────────────────────────────────────────────────────


class InterviewSummaryResponse(BaseModel):
    """Context fields returned with an interview session."""

    job_description: str | None
    scoring_rubric: str | None
    ai_assessment: str | None
    status: str | None


class InterviewResponse(BaseModel):
    """Full interview session response."""

    id: UUID
    title: str | None
    status: str | None
    role_title: str | None
    platform: str | None
    ai_tone: str | None
    candidate_name: str
    candidate_email: str | None
    summary: InterviewSummaryResponse | None
    created_at: datetime | None

    model_config = {"from_attributes": True}


# ── Enums ──────────────────────────────────────────────────────────────────────


class InterviewStatus(str, Enum):
    draft = "draft"
    scheduled = "scheduled"
    processing = "processing"
    completed = "completed"


class TranscriptStatus(str, Enum):
    processing = "processing"
    ready = "ready"
    failed = "failed"


# ── Scorecard schemas ──────────────────────────────────────────────────────────


class ScorecardScoreRequest(BaseModel):
    """A single category score submitted by the interviewer."""

    category_id: UUID
    score_pct: int = Field(..., ge=0, le=100)


class ScorecardSubmitRequest(BaseModel):
    """Request body for PATCH /interviews/:id/scorecard."""

    overall_rating: int = Field(..., ge=1, le=5)
    scores: list[ScorecardScoreRequest] = Field(..., min_length=1)


class ScorecardScoreResponse(BaseModel):
    """A single score row returned in the scorecard response."""

    category_id: UUID
    category_name: str
    score_pct: int

    model_config = {"from_attributes": True}


class ScorecardResponse(BaseModel):
    """Returned after a scorecard submit or update."""

    scorecard_id: UUID
    interview_id: UUID
    overall_rating: int | None
    scores: list[ScorecardScoreResponse]
    updated_at: datetime | None

    model_config = {"from_attributes": True}


# ── Candidate profile schemas ──────────────────────────────────────────────────


class CandidateResponse(BaseModel):
    id: UUID
    full_name: str
    email: str | None
    phone: str | None
    avatar_initials: str | None
    resume_url: str | None
    portfolio_url: str | None

    model_config = {"from_attributes": True}


class InterviewMetaResponse(BaseModel):
    """
    Interview fields returned inside the profile.
    Separate from any broader InterviewResponse schema.
    """

    id: UUID
    role_title: str | None
    status: InterviewStatus | None
    scheduled_start: datetime | None
    scheduled_end: datetime | None
    duration_min: int | None
    platform: str | None
    ai_tone: str | None
    questions_asked: int | None
    questions_total: int | None
    rating: int | None

    model_config = {"from_attributes": True}


class SummaryResponse(BaseModel):
    ai_assessment: str | None
    skills_to_assess: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)


class CandidateProfileResponse(BaseModel):
    """Response for GET /interviews/:id/profile."""

    candidate: CandidateResponse
    interview: InterviewMetaResponse
    scorecard: ScorecardResponse | None
    summary: SummaryResponse | None
    transcript_status: TranscriptStatus | None
