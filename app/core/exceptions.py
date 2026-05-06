from fastapi import HTTPException


def not_found(resource: str) -> HTTPException:
    """
    Create a standardized 404 HTTP exception.

    Args:
        resource: Name of the missing resource.

    Returns:
        HTTPException: Configured 404 exception response.
    """
    return HTTPException(
        status_code=404,
        detail={
            "status_code": 404,
            "message": f"{resource} not found",
            "data": None
        }
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
        status_code=401,
        detail={
            "status_code": 401,
            "message": message,
            "data": None
        }
    )