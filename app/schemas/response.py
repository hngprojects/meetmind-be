from typing import Any, Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class PaginationMeta(BaseModel):
    """
    Pagination metadata.

    Attributes:
        page: Current page number.
        per_page: Number of items per page.
        total: Total number of records.
        total_pages: Total number of available pages.
    """

    page: int
    per_page: int
    total: int
    total_pages: int


class APIResponse(BaseModel, Generic[T]):
    """
    Standard API response schema.

    Attributes:
        status_code: HTTP status code.
        message: Human-readable response message.
        data: Response payload.
    """
    
    status_code: int
    message: str
    data: T | None = None


class PaginatedResponse(APIResponse[list[T]], Generic[T]):
    """
    Standard paginated API response schema.

    Attributes:
        pagination: Pagination metadata.
    """
    
    pagination: PaginationMeta | None = None
