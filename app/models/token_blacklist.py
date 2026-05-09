"""Blacklisted JWT identifiers — access tokens keyed by jti, refresh tokens by hash."""

from datetime import datetime

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKey


class TokenBlacklist(Base, UUIDPrimaryKey):
    """Revoked token identifiers, retained until the token's natural expiry.

    Access tokens are keyed by their ``jti`` claim (a UUID4 embedded at
    issuance).  Refresh tokens are keyed by their SHA-256 hex digest,
    consistent with the ``RefreshToken`` table.

    Rows become inert once ``expires_at`` passes — the token would be
    rejected as expired regardless — so they can be pruned freely.
    """

    __tablename__ = "token_blacklist"

    # jti for access tokens; SHA-256 hex digest for refresh tokens.
    token_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    # "access" | "refresh"
    token_type: Mapped[str] = mapped_column(String(10), nullable=False)

    # Mirrors the token's own expiry so cleanup never touches live tokens.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        # Hot path: existence check on every authenticated request.
        # `token_id` is declared unique on the column which creates the
        # underlying unique index; avoid declaring a duplicate index here.
        # Cleanup path: DELETE FROM token_blacklist WHERE expires_at < now()
        Index("ix_token_blacklist_expires_at", "expires_at"),
    )