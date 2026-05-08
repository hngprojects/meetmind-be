"""merge migration branches

Revision ID: b9d35164e0f9
Revises: 64a8c4b4d071, 864df66fbeb7, 8d114ef61fcc, e6bc25e32942
Create Date: 2026-05-07 21:49:19.602564

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b9d35164e0f9'
down_revision: Union[str, None] = ('64a8c4b4d071', '864df66fbeb7', '8d114ef61fcc', 'e6bc25e32942')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
