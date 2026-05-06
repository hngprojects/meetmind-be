"""
Auth endpoints
"""

from fastapi import APIRouter, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.api.deps import DBSession
from app.core.config import settings
from app.schemas.auth import ForgotPasswordRequest
from app.schemas.response import APIResponse
from app.services.auth import request_password_reset

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.post("/forgot-password", status_code=200)
@limiter.limit("5/minute" if not settings.TESTING else "1000/minute")
async def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    db: DBSession,
) -> APIResponse:
    """
    Handle forgot-password requests.

    Accepts an email address and triggers the password-reset workflow.

    For security reasons, the response is always identical regardless of
    whether the email exists in the system. This prevents account
    enumeration attacks.

    Args:
        body: Request payload containing the user's email address.
        request: Incoming FastAPI request object.
        db: Database session dependency.

    Returns:
        APIResponse: Standardized success response.
    """
    await request_password_reset(db=db, email=str(body.email))

    return APIResponse(
        status_code=200,
        message="If an account with that email exists, a reset link has been sent.",
        data=None,
    )