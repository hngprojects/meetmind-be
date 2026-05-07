"""merge team heads

Revision ID: 795da51cf53f
Revises: 6b9e386f0678
Create Date: 2026-05-07 17:13:03.053335

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '795da51cf53f'
down_revision: Union[str, None] = '6b9e386f0678'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
