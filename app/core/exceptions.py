"""Domain-specific exception hierarchy.

These exceptions are raised by services and routes to signal business-rule
violations. The route layer (or central handlers in :mod:`app.main`) maps
them to :class:`app.core.responses.APIError` so clients always receive the
standardized error envelope.
"""

from fastapi import HTTPException
from fastapi import status



class AppBaseException(Exception):
    """Base class for all domain-specific errors raised inside the app.

    Subclass this for any new domain exception so callers can catch the
    family with a single ``except AppBaseException`` block.
    """


class UserAlreadyExistsException(AppBaseException):
    """Raised when attempting to register an email that is already in use.

    Attributes:
        email: The conflicting email address.
    """

    def __init__(self, email: str) -> None:
        """Initialize the exception with the conflicting email.

        Args:
            email: The email address that is already registered.
        """
        self.email = email
        super().__init__(f"Email '{email}' is already registered.")



# ==========================================================================
# HTTP Exception Helpers
# ==========================================================================

def not_found(resource: str) -> HTTPException:
    """
    Create a standardized 404 HTTP exception.

    Args:
        resource: Name of the missing resource.

    Returns:
        HTTPException: Configured 404 exception response.
    """
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{resource} not found",
    )



def unauthorized(message: str = "Authentication required") -> HTTPException:
    """
    Create a standardized 401 HTTP exception.

    Args:
        message: Custom authentication error message.

    Returns:
        HTTPException: Configured 401 exception response.
    """
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=message,
    )
