"""merge_heads

Revision ID: 626d4ab1492c
Revises: 3b2b691c7f46, 8ba95b973a4a
Create Date: 2026-05-09 19:28:49.137402

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '626d4ab1492c'
down_revision: Union[str, None] = ('3b2b691c7f46', '8ba95b973a4a')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
