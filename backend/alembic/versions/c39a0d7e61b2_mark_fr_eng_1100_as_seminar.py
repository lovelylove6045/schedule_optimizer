"""Mark FR ENG 1100 as a seminar.

Revision ID: c39a0d7e61b2
Revises: 4c8f31d10a7b
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c39a0d7e61b2"
down_revision: str | Sequence[str] | None = "4c8f31d10a7b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Classify the catalog's FR ENG 1100 row as a seminar when it is present."""
    op.execute("UPDATE courses SET course_type = 'SEMINAR' WHERE course_id = 2160")


def downgrade() -> None:
    """Restore the pre-correction FR ENG 1100 classification."""
    op.execute("UPDATE courses SET course_type = 'STANDARD' WHERE course_id = 2160")
