from fastapi import APIRouter, status

from app.api import deps
from app.core.responses import APIError, APIResponse, success
from app.schemas.dashboard import DashboardCompleted, DashboardSchedule
from app.services.dashboard_service import DashboardService

router = APIRouter()


@router.get("/schedule", response_model=APIResponse[list[DashboardSchedule]])
async def get_dashboard_schedule(db: deps.DBSession, user: deps.CurrentUser):
    """
    Fetch optimized upcoming interview schedule for the dashboard.
    Returns success envelope with a list of DashboardSchedule objects.
    """
    try:
        interviews = await DashboardService.get_upcoming_schedule(db, user.id)

        # Mapping DB models to Pydantic Schema with safe fallbacks
        data = [
            DashboardSchedule(
                id=i.id,
                candidate_name=(
                    i.candidate.full_name if i.candidate else "Unknown Candidate"
                ),
                role_title=i.role_title or "Role Pending",
                scheduled_start=i.scheduled_start,
                platform=i.platform or "Standard",
            )
            for i in interviews
        ]

        return success(
            data=data, message="Upcoming dashboard schedule retrieved successfully"
        )

    except Exception:
        # standardizing the error response for the frontend
        raise APIError(
            message=(
                "We encountered an issue loading your schedule. Please try again later."
            ),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="dashboard_schedule_error",
        )


@router.get("/completed", response_model=APIResponse[list[DashboardCompleted]])
async def get_dashboard_completed(db: deps.DBSession, user: deps.CurrentUser):
    """
    Fetch last 5 completed interviews.
    Implements Curveball Logic: Falls back to 85.0 if rating is unavailable.
    """
    try:
        interviews = await DashboardService.get_completed_interviews(db, user.id)

        data = []
        for i in interviews:
            # THE STAGE 5 CURVEBALL:
            # Graceful degradation for the stakeholder demo
            # We treat 'rating' as the score field.
            score = float(i.rating) if i.rating is not None else 85.0

            data.append(
                DashboardCompleted(
                    id=i.id,
                    candidate_name=i.candidate.full_name if i.candidate else "N/A",
                    score=score,
                    completed_at=i.scheduled_end,
                    status="Evaluated",
                )
            )

        return success(
            data=data, message="Recent performance feed retrieved successfully"
        )

    except Exception:
        raise APIError(
            message="Could not retrieve recent performance data.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="dashboard_completed_error",
        )
