"""drop unused academic_programs.degree_type

Revision ID: 564dcc9e0b41
Revises: 1b0db359d548
Create Date: 2026-08-12 03:07:20.782025

Reverts part of 1b0db359d548: the optimizer only needs a program's
requirement tree, not whether it grants a BS vs. BA vs. nothing, so
`degree_type` was removed again shortly after being added (see
db/SUMMARY.md Sec.7 for the full story). Hand-edited (like 1b0db359d548) to
also drop the now-orphaned `degree_type` Postgres enum type, which
autogenerate detects for the column but not for the type itself.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '564dcc9e0b41'
down_revision: Union[str, Sequence[str], None] = '1b0db359d548'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

degree_type = postgresql.ENUM("BS", "BA", "NONE", name="degree_type")


def upgrade() -> None:
    op.drop_column('academic_programs', 'degree_type')
    degree_type.drop(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    degree_type.create(op.get_bind(), checkfirst=True)
    op.add_column('academic_programs', sa.Column('degree_type', degree_type, autoincrement=False, nullable=True))
