"""Candidate endpoints."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DBSession
from app.models.interview import (
    Candidate,
    Interview,
    InterviewHighlight,
    InterviewRedFlag,
    InterviewSkillToAssess,
    InterviewSummary,
)
from app.schemas.candidate import CandidateProfileOut

router = APIRouter()


@router.get("/{candidate_id}", response_model=CandidateProfileOut)
async def get_candidate(
    candidate_id: UUID,
    db: DBSession,
    current_user: CurrentUser,
):
    """Get full profile for a single candidate including all interviews,
    computed stats, and AI summary data."""

    # ── 1. Candidate ──────────────────────────────────────────
    result = await db.execute(select(Candidate).where(Candidate.id == candidate_id))
    candidate = result.scalar_one_or_none()

    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found",
        )

    # ── 2. Interviews ─────────────────────────────────────────
    result = await db.execute(
        select(Interview)
        .where(Interview.candidate_id == candidate_id)
        .order_by(Interview.scheduled_start.desc())
    )
    interviews = result.scalars().all()

    interview_ids = [i.id for i in interviews]

    # ── 3. Summaries ──────────────────────────────────────────
    summary_map = {}
    summary_ids = []
    if interview_ids:
        result = await db.execute(
            select(InterviewSummary).where(
                InterviewSummary.interview_id.in_(interview_ids)
            )
        )
        for s in result.scalars().all():
            summary_map[s.interview_id] = s
            summary_ids.append(s.id)

    # ── 4. Highlights, Red Flags, Skills ──────────────────────
    highlights_map: dict = {}
    red_flags_map: dict = {}
    skills_map: dict = {}

    if summary_ids:
        result = await db.execute(
            select(InterviewHighlight)
            .where(InterviewHighlight.summary_id.in_(summary_ids))
            .order_by(InterviewHighlight.sort_order)
        )
        for h in result.scalars().all():
            highlights_map.setdefault(h.summary_id, []).append(h)

        result = await db.execute(
            select(InterviewRedFlag)
            .where(InterviewRedFlag.summary_id.in_(summary_ids))
            .order_by(InterviewRedFlag.sort_order)
        )
        for r in result.scalars().all():
            red_flags_map.setdefault(r.summary_id, []).append(r)

        result = await db.execute(
            select(InterviewSkillToAssess)
            .where(InterviewSkillToAssess.summary_id.in_(summary_ids))
            .order_by(InterviewSkillToAssess.sort_order)
        )
        for s in result.scalars().all():
            skills_map.setdefault(s.summary_id, []).append(s)

    # ── 5. Stats ──────────────────────────────────────────────
    total = len(interviews)
    completed = sum(1 for i in interviews if i.status == "completed")
    scheduled = sum(1 for i in interviews if i.status == "scheduled")
    ratings = [i.rating for i in interviews if i.rating is not None]
    avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else None

    # ── 6. Assemble ───────────────────────────────────────────
    interviews_out = []
    for interview in interviews:
        summary = summary_map.get(interview.id)
        sid = summary.id if summary else None
        interviews_out.append(
            {
                "id": interview.id,
                "role_title": interview.role_title,
                "status": interview.status,
                "platform": interview.platform,
                "scheduled_start": interview.scheduled_start,
                "duration_min": interview.duration_min,
                "rating": interview.rating,
                "questions_asked": interview.questions_asked,
                "questions_total": interview.questions_total,
                "summary": {
                    "ai_assessment": summary.ai_assessment if summary else None,
                    "status": summary.status if summary else None,
                    "highlights": [
                        {"content": h.content, "sort_order": h.sort_order}
                        for h in highlights_map.get(sid, [])
                    ],
                    "red_flags": [
                        {"content": r.content, "sort_order": r.sort_order}
                        for r in red_flags_map.get(sid, [])
                    ],
                    "skills_assessed": [
                        {"skill": s.skill, "sort_order": s.sort_order}
                        for s in skills_map.get(sid, [])
                    ],
                }
                if summary
                else None,
            }
        )

    return {
        "id": candidate.id,
        "full_name": candidate.full_name,
        "email": candidate.email,
        "phone": candidate.phone,
        "avatar_initials": candidate.avatar_initials,
        "resume_url": candidate.resume_url,
        "portfolio_url": candidate.portfolio_url,
        "stats": {
            "total_interviews": total,
            "completed": completed,
            "scheduled": scheduled,
            "average_rating": avg_rating,
        },
        "interviews": interviews_out,
    }
