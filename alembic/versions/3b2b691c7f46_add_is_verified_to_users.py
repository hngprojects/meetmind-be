"""add is_verified to users

Revision ID: 3b2b691c7f46
Revises: 6a2d8a454e64
Create Date: 2026-05-09 07:01:47.589100

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '3b2b691c7f46'
down_revision: Union[str, None] = '6a2d8a454e64'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "is_verified")
