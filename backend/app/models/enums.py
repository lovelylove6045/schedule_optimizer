"""Python-side enum definitions backing real Postgres native ENUM types.

These mirror most of "Appendix A: Recommended Controlled Values" in
`Stellic_Degree_Optimizer_Database_Design.pdf`: program_type,
requirement_node_type, rule_operator, requisite_type, course_relation_type,
scenario_program_role, scenario_preference_type, and the optimization
objective codes. Wiring these up as native Postgres ENUM types (instead of
unconstrained `String`) means the *database* now rejects a bad value at
insert time, not just application code.

Appendix A also lists `degree_type` (BS/BA/NONE), but it isn't modeled here:
the optimizer only ever needs to know a program's *requirement tree*, not
whether it happens to grant a BS vs. a BA vs. nothing (a minor's
`program_type` already says it isn't a degree at all) — so it was added,
then deliberately removed again, to keep the schema to what's actually used
(see `db/SUMMARY.md` §7 for the full story).

`RULE_OPERATOR_ENUM` is intentionally a single shared enum, reused by both
`requirement_nodes.node_operator` and `course_rule_nodes.rule_operator`,
since Appendix A defines `rule_operator` once for both rule trees.

One enum here is NOT in Appendix A: `CourseRuleNodeType`
(`course_rule_nodes.node_type`). The PDF describes this column only in prose
("group, course, course group, standing, exam, consent, and other leaf
types") and never pins it to Appendix A's `requirement_node_type` list —
which makes sense, since that list's ROOT/CONSTRAINT/NON_COURSE values are
for the *other* tree (`requirement_nodes`) and don't apply to a prerequisite
rule. Its exact value set (including `OTHER`, `PROGRAM_MEMBERSHIP`,
`SUBJECT_LEVEL`, `CREDIT_HOURS`) is taken directly from the real, already-
structured `schedule_optimizer_db/course_rule_nodes.json`, loaded verbatim
by `db/load_catalog.py` — see `db/SUMMARY.md` for why no free-text parsing
is needed for this table.

`RequirementNodeType.CREDIT_REQUIREMENT` was likewise added because it's a
real value present in `schedule_optimizer_db/requirement_nodes.json` (used
for a handful of "just require N credit hours from an unlisted/placeholder
source" nodes, e.g. ROTC course-slots not yet in the `courses` table).
"""

from __future__ import annotations

import enum

from sqlalchemy import Enum as SqlEnum


class ProgramType(str, enum.Enum):
    MAJOR = "MAJOR"
    MINOR = "MINOR"
    EMPHASIS = "EMPHASIS"
    CERTIFICATE = "CERTIFICATE"
    UNIVERSITY_CORE = "UNIVERSITY_CORE"


class RequirementNodeType(str, enum.Enum):
    ROOT = "ROOT"
    GROUP = "GROUP"
    COURSE = "COURSE"
    COURSE_GROUP = "COURSE_GROUP"
    CONSTRAINT = "CONSTRAINT"
    NON_COURSE = "NON_COURSE"
    CREDIT_REQUIREMENT = "CREDIT_REQUIREMENT"


class RuleOperator(str, enum.Enum):
    ALL = "ALL"
    ANY = "ANY"
    N_OF = "N_OF"
    CREDITS_FROM = "CREDITS_FROM"
    UNITS_FROM = "UNITS_FROM"


class RequisiteType(str, enum.Enum):
    PREREQUISITE = "PREREQUISITE"
    COREQUISITE = "COREQUISITE"
    PRE_OR_COREQUISITE = "PRE_OR_COREQUISITE"
    RECOMMENDED = "RECOMMENDED"


class CourseRuleNodeType(str, enum.Enum):
    GROUP = "GROUP"
    COURSE = "COURSE"
    COURSE_GROUP = "COURSE_GROUP"
    STANDING = "STANDING"
    EXAM = "EXAM"
    CONSENT = "CONSENT"
    OTHER = "OTHER"
    PROGRAM_MEMBERSHIP = "PROGRAM_MEMBERSHIP"
    SUBJECT_LEVEL = "SUBJECT_LEVEL"
    CREDIT_HOURS = "CREDIT_HOURS"


class CourseRelationType(str, enum.Enum):
    EQUIVALENT = "EQUIVALENT"
    CROSS_LISTED = "CROSS_LISTED"
    SUBSTITUTES_FOR = "SUBSTITUTES_FOR"
    MUTUALLY_EXCLUSIVE = "MUTUALLY_EXCLUSIVE"
    DUPLICATE_CREDIT = "DUPLICATE_CREDIT"


class ScenarioProgramRole(str, enum.Enum):
    PRIMARY_MAJOR = "PRIMARY_MAJOR"
    SECOND_MAJOR = "SECOND_MAJOR"
    MINOR = "MINOR"
    EMPHASIS = "EMPHASIS"


class ScenarioPreferenceType(str, enum.Enum):
    REQUIRE_COURSE = "REQUIRE_COURSE"
    PREFER_COURSE = "PREFER_COURSE"
    AVOID_COURSE = "AVOID_COURSE"
    FIX_COURSE_TO_TERM = "FIX_COURSE_TO_TERM"
    PREFER_TAG = "PREFER_TAG"
    AVOID_TAG = "AVOID_TAG"


class OptimizationObjectiveType(str, enum.Enum):
    EARLIEST_GRADUATION = "EARLIEST_GRADUATION"
    MIN_ADDITIONAL_CREDITS = "MIN_ADDITIONAL_CREDITS"
    MAX_REQUIREMENT_OVERLAP = "MAX_REQUIREMENT_OVERLAP"
    BALANCED_WORKLOAD = "BALANCED_WORKLOAD"
    MIN_SUMMER_ENROLLMENT = "MIN_SUMMER_ENROLLMENT"
    MAX_INTEREST_ALIGNMENT = "MAX_INTEREST_ALIGNMENT"
    PRESERVE_FLEXIBILITY = "PRESERVE_FLEXIBILITY"


def _values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


# Shared SqlAlchemy `Enum` instances: import and reuse the *same* object
# across every column/model that needs it, so Alembic/SQLAlchemy treat it as
# one Postgres CREATE TYPE, not a duplicate per column.
PROGRAM_TYPE_ENUM = SqlEnum(ProgramType, name="program_type", values_callable=_values)
REQUIREMENT_NODE_TYPE_ENUM = SqlEnum(
    RequirementNodeType, name="requirement_node_type", values_callable=_values
)
RULE_OPERATOR_ENUM = SqlEnum(RuleOperator, name="rule_operator", values_callable=_values)
REQUISITE_TYPE_ENUM = SqlEnum(RequisiteType, name="requisite_type", values_callable=_values)
COURSE_RULE_NODE_TYPE_ENUM = SqlEnum(
    CourseRuleNodeType, name="course_rule_node_type", values_callable=_values
)
COURSE_RELATION_TYPE_ENUM = SqlEnum(
    CourseRelationType, name="course_relation_type", values_callable=_values
)
SCENARIO_PROGRAM_ROLE_ENUM = SqlEnum(
    ScenarioProgramRole, name="scenario_program_role", values_callable=_values
)
SCENARIO_PREFERENCE_TYPE_ENUM = SqlEnum(
    ScenarioPreferenceType, name="scenario_preference_type", values_callable=_values
)
OPTIMIZATION_OBJECTIVE_TYPE_ENUM = SqlEnum(
    OptimizationObjectiveType, name="optimization_objective_type", values_callable=_values
)
