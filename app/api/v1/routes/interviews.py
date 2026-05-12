"""Interview, session management , candidate, transcript, summary,
and scorecard endpoints."""

import logging
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser
from app.core.responses import success
from app.db.session import get_session
from app.schemas.interview import (
    CreateInterviewRequest,
    ScorecardSubmitRequest,
)
from app.services.interview import InterviewService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_interview(
    payload: CreateInterviewRequest,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """Create a new interview session with context.

    Creates a candidate record, an interview session in ``draft`` status,
    and an interview summary holding the job description and scoring rubric.

    Args:
        payload: Validated interview creation payload.
        user: The authenticated user — becomes the interviewer.
        db: Async database session.

    Returns:
        A standardized success envelope with the created interview session.

    Raises:
        APIError: 500 for any unexpected failure.
    """
    interview = await InterviewService.create_interview(payload, db, user)
    return success(
        interview.model_dump(mode="json"),
        message="Interview session created successfully",
        status_code=status.HTTP_201_CREATED,
    )


@router.get("/{interview_id}", status_code=status.HTTP_200_OK)
async def get_interview(
    interview_id: uuid.UUID,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """Retrieve an interview session by ID.

    Only returns sessions where the authenticated user is the interviewer.

    Args:
        interview_id: UUID of the interview to retrieve.
        user: The authenticated user.
        db: Async database session.

    Returns:
        A standardized success envelope with the interview session data.

    Raises:
        APIError: 404 if the interview does not exist or belongs to another user.
    """
    interview = await InterviewService.get_interview(interview_id, db, user)
    return success(
        interview.model_dump(mode="json"),
        message="Interview session retrieved successfully",
    )


@router.patch(
    "/{interview_id}/scorecard",
    status_code=status.HTTP_200_OK,
    response_model=dict,
)
async def submit_scorecard(
    interview_id: uuid.UUID,
    payload: ScorecardSubmitRequest,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """
    Submit or update the final scorecard for a completed interview.

    Validates:
    - interview ownership
    - completed interview status
    - workspace scorecard categories

    Then:
    - upserts InterviewScorecard
    - upserts ScorecardScore rows
    - updates Interview.rating

    Args:
        interview_id: UUID of the interview.
        payload: Validated scorecard submission payload.
        user: Authenticated user.
        db: Async database session.

    Returns:
        Standardized success envelope containing scorecard data.
    """
    scorecard = await InterviewService.submit_scorecard(
        interview_id=interview_id,
        request=payload,
        db=db,
        user=user,
    )

    return success(
        scorecard.model_dump(mode="json"),
        message="Interview scorecard submitted successfully",
    )


@router.get(
    "/{interview_id}/profile",
    status_code=status.HTTP_200_OK,
    response_model=dict,
)
async def get_candidate_profile(
    interview_id: uuid.UUID,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """
    Retrieve the aggregated candidate profile linked to an interview.

    Aggregates:
    - candidate details
    - interview metadata
    - scorecard
    - AI summary
    - transcript status

    Missing related resources return null instead of 404.

    Args:
        interview_id: UUID of the interview.
        user: Authenticated user.
        db: Async database session.

    Returns:
        Standardized success envelope containing candidate profile data.
    """
    profile = await InterviewService.get_candidate_profile(
        interview_id=interview_id,
        db=db,
        user=user,
    )

    return success(
        profile.model_dump(mode="json"),
        message="Candidate profile retrieved successfully",
    )
