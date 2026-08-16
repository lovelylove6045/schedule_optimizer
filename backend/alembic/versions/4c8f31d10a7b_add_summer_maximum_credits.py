"""Add a scenario-level summer credit maximum.

Revision ID: 4c8f31d10a7b
Revises: e72bac3a2d86
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4c8f31d10a7b"
down_revision: str | Sequence[str] | None = "e72bac3a2d86"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the independently configurable summer maximum with a nine-credit default."""
    op.add_column(
        "planning_scenarios",
        sa.Column("summer_maximum_credits", sa.Numeric(4, 1), nullable=False, server_default="9"),
    )


def downgrade() -> None:
    """Remove the scenario-level summer maximum."""
    op.drop_column("planning_scenarios", "summer_maximum_credits")
