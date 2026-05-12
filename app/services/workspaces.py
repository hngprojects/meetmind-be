import uuid

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.responses import APIError
from app.models.workspace import WorkspaceMember


async def validate_workspace_membership(
    db: AsyncSession, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> WorkspaceMember:
    """Validate that a user is a member of a specific workspace.

    Raises APIError 403 if membership is not found.
    """
    stmt = select(WorkspaceMember).where(
        WorkspaceMember.workspace_id == workspace_id,
        WorkspaceMember.user_id == user_id,
    )
    membership = await db.scalar(stmt)

    if not membership:
        raise APIError(
            message="You do not have access to this workspace.",
            status_code=status.HTTP_403_FORBIDDEN,
            code="forbidden",
        )

    return membership
