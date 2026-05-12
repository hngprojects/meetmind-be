import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import CurrentUser, DBSession
from app.core.responses import success
from app.schemas.candidates import CandidateStatsResponse
from app.services.candidates import get_candidate_stats
from app.services.workspaces import validate_workspace_membership

router = APIRouter()


@router.get("/stats")
async def fetch_candidate_stats(
    workspace_id: uuid.UUID = Query(..., description="The unique ID of the workspace"),
    db: DBSession = None,
    current_user: CurrentUser = None,
):
    """Retrieve aggregated candidate statistics for a specific workspace.

    This endpoint calculates real-time counters for the recruitment dashboard,
    including total interviews, completed sessions, and items needing attention.

    Args:
        workspace_id: The ID of the workspace to aggregate statistics for.
        db: Async database session injected by FastAPI.
        current_user: The authenticated user making the request.

    Returns:
        A standardized success envelope containing:
        - total: Total number of interviews.
        - completed: Count of finished interviews.
        - ongoing: Count of active or live sessions.
        - needs_attention: Count of failed or problematic interviews.

    Raises:
        APIError: 403 if the user is not a member of the workspace.
        APIError: 401 if the user is unauthenticated.
    """
    # Enforce multi-tenancy and workspace membership
    await validate_workspace_membership(db, workspace_id, current_user.id)

    # Execute optimized database-level aggregation
    stats = await get_candidate_stats(db, workspace_id=workspace_id)

    return success(
        data=stats, 
        message="Candidate statistics fetched successfully"
    )
