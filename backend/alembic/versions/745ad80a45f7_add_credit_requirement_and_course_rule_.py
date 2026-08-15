"""add credit_requirement and course_rule_node_type enum values

Switching to loading schedule_optimizer_db/course_rule_nodes.json and
requirement_nodes.json verbatim (see db/SUMMARY.md) surfaced real
node_type values that weren't in our enums yet:

- requirement_node_type: CREDIT_REQUIREMENT
- course_rule_node_type: OTHER, PROGRAM_MEMBERSHIP, SUBJECT_LEVEL,
  CREDIT_HOURS

Postgres requires ALTER TYPE ... ADD VALUE to run outside an explicit
transaction block, hence op.get_context().autocommit_block(). Postgres
has no ALTER TYPE ... DROP VALUE, so downgrade() is a documented no-op
(existing rows using these values would have to be migrated off them
first, by hand, before a real downgrade could drop the whole type).

Revision ID: 745ad80a45f7
Revises: 564dcc9e0b41
Create Date: 2026-08-13 23:25:45.711629

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '745ad80a45f7'
down_revision: Union[str, Sequence[str], None] = '564dcc9e0b41'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE requirement_node_type ADD VALUE IF NOT EXISTS 'CREDIT_REQUIREMENT'")
        op.execute("ALTER TYPE course_rule_node_type ADD VALUE IF NOT EXISTS 'OTHER'")
        op.execute("ALTER TYPE course_rule_node_type ADD VALUE IF NOT EXISTS 'PROGRAM_MEMBERSHIP'")
        op.execute("ALTER TYPE course_rule_node_type ADD VALUE IF NOT EXISTS 'SUBJECT_LEVEL'")
        op.execute("ALTER TYPE course_rule_node_type ADD VALUE IF NOT EXISTS 'CREDIT_HOURS'")


def downgrade() -> None:
    """Downgrade schema.

    Postgres can't drop a single enum value (ALTER TYPE ... DROP VALUE
    doesn't exist). Reversing this cleanly would mean creating a new type
    without these values, rewriting every row that uses them, and
    swapping the type in -- not worth automating for values that are
    already required by real source data. No-op.
    """
    pass
