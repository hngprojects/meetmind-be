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
    def reject_blank(cls, v: str) -> str:
        """
        Prevent empty or whitespace-only email values.

        Args:
            v: Raw email input value.

        Returns:
            str: Sanitized email value.

        Raises:
            ValueError: If the email is empty.
        """
        if not v or not v.strip():
            raise ValueError("Email is required")
        return v
