from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    """
    Handle request validation errors.

    Transforms FastAPI validation errors into the application's
    standardized API response format.

    Args:
        request: Incoming FastAPI request object.
        exc: Validation exception raised by FastAPI.

    Returns:
        JSONResponse: Structured validation error response.
    """
    errors = []

    for err in exc.errors():
        field = err["loc"][-1]

        if field == "email":
            message = "A valid email address is required"
        else:
            message = "Invalid input"

        errors.append({
            "field": field,
            "message": message,
        })

    return JSONResponse(
        status_code=422,
        content={
            "status_code": 422,
            "message": "Validation failed",
            "data": None,
            "errors": errors,
        },
    )