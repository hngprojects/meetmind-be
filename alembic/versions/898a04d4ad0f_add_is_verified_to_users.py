"""add is_verified to users

Revision ID: 898a04d4ad0f
Revises: b9d35164e0f9
Create Date: 2026-05-07 23:47:40.630363

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '898a04d4ad0f'
down_revision: Union[str, None] = 'b9d35164e0f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('is_verified', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('password_reset_tokens', sa.Column('updated_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('password_reset_tokens', 'updated_at')
    op.drop_column('users', 'is_verified')
