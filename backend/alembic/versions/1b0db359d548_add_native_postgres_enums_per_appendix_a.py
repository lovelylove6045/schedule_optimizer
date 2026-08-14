"""add native postgres enums per appendix a

Revision ID: 1b0db359d548
Revises: a1d053466018
Create Date: 2026-08-12 02:54:34.595464

Hand-written (not left as raw autogenerate output): Alembic's autogenerate
correctly *detects* every enum-ification and the two scenario_programs
column changes, but it doesn't emit the Postgres-specific DDL a varchar ->
enum conversion actually needs on a table that already has rows — it leaves
out `CREATE TYPE ...` entirely and generates a plain `ALTER COLUMN ... TYPE`
with no `USING` cast, which Postgres rejects (there is no implicit
varchar->enum cast). Every ALTER below explicitly creates the enum type
first and casts the existing text through `::text::<enum>`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '1b0db359d548'
down_revision: Union[str, Sequence[str], None] = 'a1d053466018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


program_type = postgresql.ENUM(
    "MAJOR", "MINOR", "EMPHASIS", "CERTIFICATE", "UNIVERSITY_CORE", name="program_type"
)
degree_type = postgresql.ENUM("BS", "BA", "NONE", name="degree_type")
requirement_node_type = postgresql.ENUM(
    "ROOT", "GROUP", "COURSE", "COURSE_GROUP", "CONSTRAINT", "NON_COURSE",
    name="requirement_node_type",
)
rule_operator = postgresql.ENUM(
    "ALL", "ANY", "N_OF", "CREDITS_FROM", "UNITS_FROM", name="rule_operator"
)
requisite_type = postgresql.ENUM(
    "PREREQUISITE", "COREQUISITE", "PRE_OR_COREQUISITE", "RECOMMENDED", name="requisite_type"
)
course_rule_node_type = postgresql.ENUM(
    "GROUP", "COURSE", "COURSE_GROUP", "STANDING", "EXAM", "CONSENT", "TEXT",
    name="course_rule_node_type",
)
course_relation_type = postgresql.ENUM(
    "EQUIVALENT", "CROSS_LISTED", "SUBSTITUTES_FOR", "MUTUALLY_EXCLUSIVE", "DUPLICATE_CREDIT",
    name="course_relation_type",
)
scenario_program_role = postgresql.ENUM(
    "PRIMARY_MAJOR", "SECOND_MAJOR", "MINOR", "EMPHASIS", name="scenario_program_role"
)
scenario_preference_type = postgresql.ENUM(
    "REQUIRE_COURSE", "PREFER_COURSE", "AVOID_COURSE", "FIX_COURSE_TO_TERM",
    "PREFER_TAG", "AVOID_TAG", name="scenario_preference_type",
)
optimization_objective_type = postgresql.ENUM(
    "EARLIEST_GRADUATION", "MIN_ADDITIONAL_CREDITS", "MAX_REQUIREMENT_OVERLAP",
    "BALANCED_WORKLOAD", "MIN_SUMMER_ENROLLMENT", "MAX_INTEREST_ALIGNMENT",
    "PRESERVE_FLEXIBILITY", name="optimization_objective_type",
)

ALL_ENUMS = [
    program_type,
    degree_type,
    requirement_node_type,
    rule_operator,
    requisite_type,
    course_rule_node_type,
    course_relation_type,
    scenario_program_role,
    scenario_preference_type,
    optimization_objective_type,
]


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in ALL_ENUMS:
        enum_type.create(bind, checkfirst=True)

    # academic_programs.program_type: VARCHAR(20) -> program_type enum
    op.execute(
        "ALTER TABLE academic_programs ALTER COLUMN program_type "
        "TYPE program_type USING program_type::text::program_type"
    )
    op.add_column("academic_programs", sa.Column("degree_type", degree_type, nullable=True))

    # course_relations.relation_type: VARCHAR(30) -> course_relation_type enum
    op.execute(
        "ALTER TABLE course_relations ALTER COLUMN relation_type "
        "TYPE course_relation_type USING relation_type::text::course_relation_type"
    )

    # course_rule_nodes: requisite_type, node_type, rule_operator
    op.execute(
        "ALTER TABLE course_rule_nodes ALTER COLUMN requisite_type "
        "TYPE requisite_type USING requisite_type::text::requisite_type"
    )
    op.execute(
        "ALTER TABLE course_rule_nodes ALTER COLUMN node_type "
        "TYPE course_rule_node_type USING node_type::text::course_rule_node_type"
    )
    op.execute(
        "ALTER TABLE course_rule_nodes ALTER COLUMN rule_operator "
        "TYPE rule_operator USING rule_operator::text::rule_operator"
    )

    # requirement_nodes: node_type, node_operator (shares the rule_operator enum)
    op.execute(
        "ALTER TABLE requirement_nodes ALTER COLUMN node_type "
        "TYPE requirement_node_type USING node_type::text::requirement_node_type"
    )
    op.execute(
        "ALTER TABLE requirement_nodes ALTER COLUMN node_operator "
        "TYPE rule_operator USING node_operator::text::rule_operator"
    )

    # scenario_objectives.objective_type / scenario_preferences.preference_type
    # (both empty tables so far, but keep the same explicit-cast style for consistency)
    op.execute(
        "ALTER TABLE scenario_objectives ALTER COLUMN objective_type "
        "TYPE optimization_objective_type USING objective_type::text::optimization_objective_type"
    )
    op.execute(
        "ALTER TABLE scenario_preferences ALTER COLUMN preference_type "
        "TYPE scenario_preference_type USING preference_type::text::scenario_preference_type"
    )

    # scenario_programs: is_primary (bool) -> program_role (enum), empty table
    op.add_column(
        "scenario_programs",
        sa.Column("program_role", scenario_program_role, nullable=False, server_default="PRIMARY_MAJOR"),
    )
    op.alter_column("scenario_programs", "program_role", server_default=None)
    op.drop_column("scenario_programs", "is_primary")


def downgrade() -> None:
    op.add_column(
        "scenario_programs",
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("scenario_programs", "is_primary", server_default=None)
    op.drop_column("scenario_programs", "program_role")

    op.execute(
        "ALTER TABLE scenario_preferences ALTER COLUMN preference_type "
        "TYPE VARCHAR(40) USING preference_type::text"
    )
    op.execute(
        "ALTER TABLE scenario_objectives ALTER COLUMN objective_type "
        "TYPE VARCHAR(40) USING objective_type::text"
    )
    op.execute(
        "ALTER TABLE requirement_nodes ALTER COLUMN node_operator "
        "TYPE VARCHAR(10) USING node_operator::text"
    )
    op.execute(
        "ALTER TABLE requirement_nodes ALTER COLUMN node_type "
        "TYPE VARCHAR(30) USING node_type::text"
    )
    op.execute(
        "ALTER TABLE course_rule_nodes ALTER COLUMN rule_operator "
        "TYPE VARCHAR(10) USING rule_operator::text"
    )
    op.execute(
        "ALTER TABLE course_rule_nodes ALTER COLUMN node_type "
        "TYPE VARCHAR(30) USING node_type::text"
    )
    op.execute(
        "ALTER TABLE course_rule_nodes ALTER COLUMN requisite_type "
        "TYPE VARCHAR(30) USING requisite_type::text"
    )
    op.execute(
        "ALTER TABLE course_relations ALTER COLUMN relation_type "
        "TYPE VARCHAR(30) USING relation_type::text"
    )
    op.drop_column("academic_programs", "degree_type")
    op.execute(
        "ALTER TABLE academic_programs ALTER COLUMN program_type "
        "TYPE VARCHAR(20) USING program_type::text"
    )

    bind = op.get_bind()
    for enum_type in reversed(ALL_ENUMS):
        enum_type.drop(bind, checkfirst=True)
