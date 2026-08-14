"""SQLAlchemy models, one table per file, matching docs/ARCHITECTURE.md.

Importing this package registers every model on `Base.metadata`, which is
what Alembic's autogenerate needs to see the full schema.
"""

from app.database import Base

# Catalog domain
from app.models.college import College
from app.models.department import Department
from app.models.subject import Subject
from app.models.course import Course
from app.models.course_tag import CourseTag
from app.models.course_tag_map import CourseTagMap
from app.models.course_relation import CourseRelation
from app.models.term import Term
from app.models.course_rule_node import CourseRuleNode

# Programs & requirements domain
from app.models.academic_program import AcademicProgram
from app.models.program_relationship import ProgramRelationship
from app.models.requirement_set import RequirementSet
from app.models.program_requirement_set import ProgramRequirementSet
from app.models.course_group import CourseGroup
from app.models.course_group_member import CourseGroupMember
from app.models.requirement_node import RequirementNode
from app.models.overlap_policy import OverlapPolicy

# Students & scenarios domain
from app.models.student import Student
from app.models.student_credit import StudentCredit
from app.models.planning_scenario import PlanningScenario
from app.models.scenario_program import ScenarioProgram
from app.models.scenario_term import ScenarioTerm
from app.models.scenario_preference import ScenarioPreference
from app.models.scenario_objective import ScenarioObjective

# Plans domain
from app.models.degree_plan import DegreePlan
from app.models.plan_course import PlanCourse
from app.models.requirement_allocation import RequirementAllocation
from app.models.optimization_message import OptimizationMessage

__all__ = [
    "Base",
    "College",
    "Department",
    "Subject",
    "Course",
    "CourseTag",
    "CourseTagMap",
    "CourseRelation",
    "Term",
    "CourseRuleNode",
    "AcademicProgram",
    "ProgramRelationship",
    "RequirementSet",
    "ProgramRequirementSet",
    "CourseGroup",
    "CourseGroupMember",
    "RequirementNode",
    "OverlapPolicy",
    "Student",
    "StudentCredit",
    "PlanningScenario",
    "ScenarioProgram",
    "ScenarioTerm",
    "ScenarioPreference",
    "ScenarioObjective",
    "DegreePlan",
    "PlanCourse",
    "RequirementAllocation",
    "OptimizationMessage",
]
