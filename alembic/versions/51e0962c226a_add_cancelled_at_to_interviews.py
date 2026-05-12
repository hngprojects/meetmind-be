"""add_cancelled_at_to_interviews

Revision ID: 51e0962c226a
Revises: 480a265e5923
Create Date: 2026-05-12 09:53:52.649001

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '51e0962c226a'
down_revision: Union[str, None] = '480a265e5923'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "interviews",
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("interviews", "cancelled_at")
