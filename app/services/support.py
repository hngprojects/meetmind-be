from sqlalchemy.ext.asyncio import AsyncSession

from app.models.support import SupportTicket
from app.schemas.support import (
    ContactSupportRequest,
    ContactSupportResponse,
)


class SupportService:
    @staticmethod
    async def create_ticket(
        payload: ContactSupportRequest,
        db: AsyncSession,
    ) -> ContactSupportResponse:

        ticket = SupportTicket(
            name=payload.name,
            email=payload.email,
            subject=payload.subject,
            message=payload.message,
        )

        db.add(ticket)
        await db.commit()
        await db.refresh(ticket)

        return ContactSupportResponse(
            ticket_id=ticket.id,
            status=ticket.status,
            created_at=ticket.created_at,
        )
