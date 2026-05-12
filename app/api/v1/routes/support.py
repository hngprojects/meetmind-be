from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.responses import success
from app.db.session import get_session
from app.schemas.support import ContactSupportRequest
from app.services.support import SupportService

router = APIRouter()


@router.post("/contact", status_code=status.HTTP_201_CREATED)
async def contact_support(
    payload: ContactSupportRequest,
    db: AsyncSession = Depends(get_session),
):
    ticket = await SupportService.create_ticket(payload, db)

    return success(
        ticket.model_dump(mode="json"),
        message="Support request submitted successfully",
        status_code=status.HTTP_201_CREATED,
    )
