import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DBSession
from app.core.responses import success
from app.services.calendar import get_calendar_appointments
from app.services.workspaces import validate_workspace_membership

router = APIRouter()


@router.get("", summary="List Calendar Appointments")
async def list_appointments(
    workspace_id: uuid.UUID = Query(..., description="The unique ID of the workspace"),
    date: Optional[date] = Query(
        None, description="Filter appointments by a specific date (ISO 8601 format)"
    ),
    db: DBSession = None,
    current_user: CurrentUser = None,
):
    """Retrieve scheduled interview appointments for the specified workspace.

    Args:
        workspace_id: The unique identifier of the workspace.
        date: Optional date filter. If omitted, returns all future appointments.
        db: Async database session injected by FastAPI.
        current_user: The authenticated user making the request.

    Returns:
        A standardized success envelope with a list of appointments, each containing
        candidate details and scheduled time slots.

    Raises:
        APIError: 403 if the user is not a member of the workspace.
        APIError: 401 if the user is unauthenticated.
    """
    # Enforce RBAC and multi-tenancy boundaries
    await validate_workspace_membership(db, workspace_id, current_user.id)

    # Fetch processed appointment data
    appointments = await get_calendar_appointments(db, workspace_id, date)

    return success(
        data={"appointments": appointments},
        message="Calendar appointments fetched successfully",
    )
