"""Interview session management service."""

from __future__ import annotations

import uuid

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.responses import APIError
from app.models.interview import (
    Candidate,
    Interview,
    InterviewHighlight,
    InterviewRedFlag,
    InterviewSkillToAssess,
    InterviewSummary,
    InterviewTranscript,
)
from app.models.scorecard import (
    InterviewScorecard,
    ScorecardCategory,
    ScorecardScore,
)
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.schemas.interview import (
    CandidateProfileResponse,
    CandidateResponse,
    CreateInterviewRequest,
    InterviewMetaResponse,
    InterviewResponse,
    InterviewSummaryResponse,
    ScorecardResponse,
    ScorecardScoreResponse,
    ScorecardSubmitRequest,
    SummaryResponse,
)


async def _get_or_create_workspace(db: AsyncSession, user: User) -> uuid.UUID:
    """Return the user's first workspace, creating a default one if none exists.

    Args:
        db: Active async database session.
        user: The authenticated user.

    Returns:
        The workspace UUID to scope the interview under.
    """
    result = await db.execute(
        select(WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user.id)
    )
    workspace_id = result.scalar_one_or_none()

    if workspace_id:
        return workspace_id

    # No workspace yet — create a default one for this user.
    workspace = Workspace(
        name=f"{user.name or user.email}'s Workspace",
        created_by=user.id,
    )
    db.add(workspace)
    await db.flush()

    member = WorkspaceMember(
        workspace_id=workspace.id,
        user_id=user.id,
        role="owner",
    )
    db.add(member)
    await db.flush()

    return workspace.id


class InterviewService:
    """Encapsulate interview session creation and retrieval."""

    @staticmethod
    async def create_interview(
        request: CreateInterviewRequest,
        db: AsyncSession,
        user: User,
    ) -> InterviewResponse:
        """Create an interview session with its context.

        Steps:
        1. Resolve or create the user's workspace.
        2. Create a Candidate record.
        3. Create an Interview record in ``draft`` status.
        4. Create an InterviewSummary record holding the context fields.

        Args:
            request: Validated interview creation payload.
            db: Active async database session.
            user: The authenticated user (becomes the interviewer).

        Returns:
            A populated :class:`InterviewResponse`.
        """
        workspace_id = await _get_or_create_workspace(db, user)

        # 1. Create candidate
        candidate = Candidate(
            workspace_id=workspace_id,
            full_name=request.candidate_name,
            email=request.candidate_email,
        )
        db.add(candidate)
        await db.flush()

        # 2. Create interview — status starts as "draft" per RFC scope
        interview = Interview(
            workspace_id=workspace_id,
            candidate_id=candidate.id,
            interviewer_id=user.id,
            role_title=request.role_title or request.title,
            platform=request.platform,
            ai_tone=request.ai_tone,
            status="draft",
        )
        db.add(interview)
        await db.flush()

        # 3. Create summary to hold context fields
        summary = InterviewSummary(
            interview_id=interview.id,
            job_description=request.job_description,
            scoring_rubric=request.scoring_rubric,
            status="pending",
        )
        db.add(summary)
        await db.commit()

        return InterviewResponse(
            id=interview.id,
            title=request.title,
            status=interview.status,
            role_title=interview.role_title,
            platform=interview.platform,
            ai_tone=interview.ai_tone,
            candidate_name=candidate.full_name,
            candidate_email=candidate.email,
            summary=InterviewSummaryResponse(
                job_description=summary.job_description,
                scoring_rubric=summary.scoring_rubric,
                ai_assessment=summary.ai_assessment,
                status=summary.status,
            ),
            created_at=interview.created_at,
        )

    @staticmethod
    async def get_interview(
        interview_id: uuid.UUID,
        db: AsyncSession,
        user: User,
    ) -> InterviewResponse:
        """Retrieve an interview session by ID.

        Only returns interviews where the authenticated user is the interviewer,
        preventing cross-user data leakage.

        Args:
            interview_id: UUID of the interview to retrieve.
            db: Active async database session.
            user: The authenticated user.

        Returns:
            A populated :class:`InterviewResponse`.

        Raises:
            APIError: 404 if the interview does not exist or does not belong
                to the requesting user.
        """
        result = await db.execute(
            select(Interview).where(
                Interview.id == interview_id,
                Interview.interviewer_id == user.id,
            )
        )
        interview = result.scalar_one_or_none()

        if not interview:
            raise APIError(
                "Interview not found",
                status_code=status.HTTP_404_NOT_FOUND,
                code="interview_not_found",
            )

        # Fetch candidate
        candidate_result = await db.execute(
            select(Candidate).where(Candidate.id == interview.candidate_id)
        )
        candidate = candidate_result.scalar_one_or_none()

        # Fetch summary (context)
        summary_result = await db.execute(
            select(InterviewSummary).where(
                InterviewSummary.interview_id == interview.id
            )
        )
        summary = summary_result.scalar_one_or_none()

        return InterviewResponse(
            id=interview.id,
            title=interview.role_title,
            status=interview.status,
            role_title=interview.role_title,
            platform=interview.platform,
            ai_tone=interview.ai_tone,
            candidate_name=candidate.full_name if candidate else "Unknown",
            candidate_email=candidate.email if candidate else None,
            summary=InterviewSummaryResponse(
                job_description=summary.job_description if summary else None,
                scoring_rubric=summary.scoring_rubric if summary else None,
                ai_assessment=summary.ai_assessment if summary else None,
                status=summary.status if summary else None,
            )
            if summary
            else None,
            created_at=interview.created_at,
        )

    @staticmethod
    async def _get_interview_or_404(
        interview_id: uuid.UUID,
        db: AsyncSession,
        user: User,
    ) -> Interview:
        """
        Fetch an interview scoped to the authenticated interviewer.

        Prevents cross-user/workspace access by ensuring the interview
        belongs to the requesting user.

        Args:
            interview_id: Interview UUID.
            db: Active async database session.
            user: Authenticated user.

        Returns:
            Interview ORM object.

        Raises:
            APIError: If interview does not exist or is inaccessible.
        """
        result = await db.execute(
            select(Interview).where(
                Interview.id == interview_id,
                Interview.interviewer_id == user.id,
            )
        )

        interview = result.scalar_one_or_none()

        if not interview:
            raise APIError(
                "Interview not found",
                status_code=status.HTTP_404_NOT_FOUND,
                code="interview_not_found",
            )

        return interview

    @staticmethod
    async def submit_scorecard(
        interview_id: uuid.UUID,
        request: ScorecardSubmitRequest,
        db: AsyncSession,
        user: User,
    ) -> ScorecardResponse:
        interview = await InterviewService._get_interview_or_404(
            interview_id=interview_id,
            db=db,
            user=user,
        )

        if interview.status != "completed":
            raise APIError(
                "Interview must be completed before scoring",
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                code="interview_not_completed",
            )

        category_ids = [score.category_id for score in request.scores]

        category_result = await db.execute(
            select(ScorecardCategory).where(
                ScorecardCategory.id.in_(category_ids),
                ScorecardCategory.workspace_id == interview.workspace_id,
            )
        )
        categories = category_result.scalars().all()

        if len(categories) != len(category_ids):
            raise APIError(
                "One or more categories do not belong to this workspace",
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                code="invalid_scorecard_category",
            )

        # Upsert scorecard
        scorecard_result = await db.execute(
            select(InterviewScorecard).where(
                InterviewScorecard.interview_id == interview.id
            )
        )
        scorecard = scorecard_result.scalar_one_or_none()

        if not scorecard:
            scorecard = InterviewScorecard(interview_id=interview.id)
            db.add(scorecard)
            await db.flush()

        # Fetch existing scores
        existing_scores_result = await db.execute(
            select(ScorecardScore).where(ScorecardScore.scorecard_id == scorecard.id)
        )
        existing_score_map = {
            s.category_id: s for s in existing_scores_result.scalars().all()
        }

        # Upsert each submitted score
        for submitted in request.scores:
            existing = existing_score_map.get(submitted.category_id)
            if existing:
                existing.score_pct = submitted.score_pct
                existing.completed = True
            else:
                db.add(
                    ScorecardScore(
                        scorecard_id=scorecard.id,
                        category_id=submitted.category_id,
                        score_pct=submitted.score_pct,
                        completed=True,  # fix #4: mark submitted scores as done
                    )
                )

        interview.rating = request.overall_rating

        await db.commit()

        # fix #2: refresh after commit so updated_at and rating are current
        await db.refresh(scorecard)
        await db.refresh(interview)

        # fix #3: join category to get name, covers pre-existing scores too
        refreshed_result = await db.execute(
            select(ScorecardScore, ScorecardCategory)
            .join(ScorecardCategory, ScorecardCategory.id == ScorecardScore.category_id)
            .where(ScorecardScore.scorecard_id == scorecard.id)
        )
        rows = refreshed_result.all()

        return ScorecardResponse(
            scorecard_id=scorecard.id,
            interview_id=interview.id,
            overall_rating=interview.rating,
            scores=[
                ScorecardScoreResponse(
                    category_id=score.category_id,
                    category_name=category.name,
                    score_pct=score.score_pct,
                )
                for score, category in rows
            ],
            updated_at=scorecard.updated_at,
        )

    @staticmethod
    async def get_candidate_profile(
        interview_id: uuid.UUID,
        db: AsyncSession,
        user: User,
    ) -> CandidateProfileResponse:
        """
        Retrieve the aggregated candidate profile for an interview.

        Aggregates:
        - candidate
        - interview metadata
        - transcript status
        - summary
        - scorecard

        Missing related resources return as null instead of 404.

        Args:
            interview_id: Interview UUID.
            db: Active async database session.
            user: Authenticated user.

        Returns:
            CandidateProfileResponse
        """
        interview = await InterviewService._get_interview_or_404(
            interview_id=interview_id,
            db=db,
            user=user,
        )

        # Candidate
        candidate_result = await db.execute(
            select(Candidate).where(Candidate.id == interview.candidate_id)
        )
        candidate = candidate_result.scalar_one()

        # Transcript
        transcript_result = await db.execute(
            select(InterviewTranscript).where(
                InterviewTranscript.interview_id == interview.id
            )
        )
        transcript = transcript_result.scalar_one_or_none()

        # Summary
        summary_result = await db.execute(
            select(InterviewSummary).where(
                InterviewSummary.interview_id == interview.id
            )
        )
        summary = summary_result.scalar_one_or_none()

        summary_response = None

        if summary:
            skills_result = await db.execute(
                select(InterviewSkillToAssess).where(
                    InterviewSkillToAssess.summary_id == summary.id
                )
            )

            highlights_result = await db.execute(
                select(InterviewHighlight).where(
                    InterviewHighlight.summary_id == summary.id
                )
            )

            red_flags_result = await db.execute(
                select(InterviewRedFlag).where(
                    InterviewRedFlag.summary_id == summary.id
                )
            )

            skills = skills_result.scalars().all()
            highlights = highlights_result.scalars().all()
            red_flags = red_flags_result.scalars().all()

            summary_response = SummaryResponse(
                ai_assessment=summary.ai_assessment,
                skills_to_assess=[skill.skill for skill in skills],
                highlights=[item.content for item in highlights],
                red_flags=[item.content for item in red_flags],
            )

        # Scorecard
        scorecard_result = await db.execute(
            select(InterviewScorecard).where(
                InterviewScorecard.interview_id == interview.id
            )
        )
        scorecard = scorecard_result.scalar_one_or_none()

        scorecard_response = None

        if scorecard:
            score_rows_result = await db.execute(
                select(ScorecardScore, ScorecardCategory)
                .join(
                    ScorecardCategory,
                    ScorecardCategory.id == ScorecardScore.category_id,
                )
                .where(ScorecardScore.scorecard_id == scorecard.id)
            )
            rows = score_rows_result.all()

            scorecard_response = ScorecardResponse(
                scorecard_id=scorecard.id,
                interview_id=interview.id,
                overall_rating=interview.rating,
                scores=[
                    ScorecardScoreResponse(
                        category_id=score.category_id,
                        category_name=category.name,
                        score_pct=score.score_pct,
                    )
                    for score, category in rows
                ],
                updated_at=scorecard.updated_at,
            )

        return CandidateProfileResponse(
            candidate=CandidateResponse(
                id=candidate.id,
                full_name=candidate.full_name,
                email=candidate.email,
                phone=candidate.phone,
                avatar_initials=candidate.avatar_initials,
                resume_url=candidate.resume_url,
                portfolio_url=candidate.portfolio_url,
            ),
            interview=InterviewMetaResponse(
                id=interview.id,
                role_title=interview.role_title,
                status=interview.status,
                scheduled_start=interview.scheduled_start,
                scheduled_end=interview.scheduled_end,
                duration_min=interview.duration_min,
                platform=interview.platform,
                ai_tone=interview.ai_tone,
                questions_asked=interview.questions_asked,
                questions_total=interview.questions_total,
                rating=interview.rating,
            ),
            scorecard=scorecard_response,
            summary=summary_response,
            transcript_status=(transcript.status if transcript else None),
        )
