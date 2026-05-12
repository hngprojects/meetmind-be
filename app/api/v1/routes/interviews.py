"""Interview, session management , candidate, transcript, summary,
and scorecard endpoints."""

import logging
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser
from app.core.responses import success
from app.db.session import get_session
from app.schemas.interview import CreateInterviewRequest, RescheduleInterviewRequest
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


@router.get("", status_code=status.HTTP_200_OK)
async def get_all_interviews(
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
    interview_status: str | None = Query(
        None,
        alias="status",
        description="Filter by interview status (e.g., live, upcoming, completed)",
    ),
):
    """Retrieve all interview sessions for the authenticated user.

    Args:
        user: The authenticated user.
        db: Async database session.

    Returns:
        A standardized success envelope with the interview sessions data.

    Raises:
        APIError: 500 for any unexpected failure.
    """
    interviews = await InterviewService.get_all_interviews(
        db, user, status_filter=interview_status
    )
    return success(
        [interview.model_dump(mode="json") for interview in interviews],
        message="Interview sessions retrieved successfully",
    )


@router.patch("/{interview_id}/reschedule", status_code=status.HTTP_200_OK)
async def reschedule_interview(
    interview_id: uuid.UUID,
    payload: RescheduleInterviewRequest,
    user: CurrentUser,
    db: AsyncSession = Depends(get_session),
):
    """Move an interview to a new date and time.

    Args:
        interview_id: UUID of the interview to reschedule.
        payload: Validated rescheduling payload.
        user: The authenticated user.
        db: Async database session.

    Returns:
        A standardized success envelope with the updated interview session.
    """
    interview = await InterviewService.reschedule_interview(
        interview_id, payload, db, user
    )
    return success(
        interview.model_dump(mode="json"),
        message="Interview rescheduled successfully",
    )
