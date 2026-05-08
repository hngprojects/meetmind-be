from fastapi import Request
from fastapi import status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


VALIDATION_MESSAGE_CATALOG: dict[str, str] = {
    "missing": "This field is required",
    "string_too_short": "Value is too short",
    "string_too_long": "Value is too long",
    "string_type": "Must be a valid string",
    "int_parsing": "Must be a valid integer",
    "float_parsing": "Must be a valid number",
    "bool_parsing": "Must be a valid boolean",
    "email_parsing": "Invalid email address",
    "value_error.email": "Invalid email address",
    "url_parsing": "Must be a valid URL",
    "literal_error": "Invalid value",
    "enum": "Invalid choice",
    "value_error": "Invalid value",
    "json_invalid": "Invalid JSON",
    "greater_than": "Value is too small",
    "less_than": "Value is too large",
    "greater_than_equal": "Value is too small",
    "less_than_equal": "Value is too large",
}


def _normalize_field(loc: tuple) -> str:
    """Normalize Pydantic error location to a stable dot-separated field path.

    Strips the leading transport segment (``body``, ``query``, ``path``) and
    joins the remaining parts with ``.`` so nested fields are readable.

    Examples:
        ``('body', 'user', 'email')`` → ``"user.email"``
        ``('query', 'page')`` → ``"page"``
        ``('body', 'email')`` → ``"email"``
    """
    parts = [str(p) for p in loc if p not in ("body", "query", "path")]
    return ".".join(parts) if parts else "body"


async def validation_exception_handler(
    request: Request,  # noqa: ARG001
    exc: RequestValidationError,
) -> JSONResponse:
    """Handle request validation errors.

    Transforms FastAPI/Pydantic validation errors into the application's
    standardized API response format using a curated message catalog keyed
    by Pydantic error ``type``. Unknown types fall back to ``"Invalid input"``.

    Args:
        request: Incoming FastAPI request object (unused).
        exc: Validation exception raised by FastAPI.

    Returns:
        JSONResponse with HTTP 422 and a list of field-level errors under
        ``errors``, each carrying ``field``, ``message``, and ``code``.
    """
    errors = []

    for err in exc.errors():
        code = err.get("type", "unknown")
        errors.append({
            "field": _normalize_field(err["loc"]),
            "message": VALIDATION_MESSAGE_CATALOG.get(code, "Invalid input"),
            "code": code,
        })

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "status_code": status.HTTP_422_UNPROCESSABLE_CONTENT,
            "message": "Validation failed",
            "data": None,
            "errors": errors,
        },
    )
