from pydantic import BaseModel, EmailStr, field_validator


class ForgotPasswordRequest(BaseModel):
    """
    Forgot-password request payload.

    Attributes:
        email: User email address.
    """

    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def reject_blank(cls, v: object) -> object:
        """
        Prevent empty or whitespace-only email values.

        Args:
            v: Raw email input value.

        Returns:
            object: Sanitized email value.

        Raises:
            ValueError: If the email is empty.
        """
        if v is None:
            raise ValueError("Email is required")
        if isinstance(v, str) and not v.strip():
            raise ValueError("Email is required")
        return v
