"""Pydantic schemas for User profile and preferences."""

import uuid

from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    """Shared fields for User schemas."""

    name: str | None = Field(None, max_length=120)
    email: EmailStr
    work_email: EmailStr | None = Field(None, max_length=255)
    avatar_url: str | None = None
    job_title: str | None = Field(None, max_length=80)
    company: str | None = Field(None, max_length=120)
    role: str | None = Field(None, max_length=60)


class UserResponse(UserBase):
    """Payload returned when fetching user profile."""

    id: uuid.UUID
    is_verified: bool

    class Config:
        from_attributes = True
