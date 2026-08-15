"""Output shape for `GET /requirement-choices`: the points in a set of programs'
requirement trees where a student genuinely gets to pick *which* course satisfies
a requirement (PDS UC-16/UC-21/UC-25 -- "MATH 1214 or MATH 1215").

The solver already explores these choices on its own; this endpoint exists so the
student can express a preference up front instead of accepting whatever the
optimizer happened to pick. A submitted pick becomes a `REQUIRE_COURSE`
`scenario_preferences` row, which `optimizer_model` already enforces as a hard
constraint."""

from typing import Literal

from pydantic import BaseModel

from app.schemas.course import CourseOut

RequirementChoiceKind = Literal["COURSE_GROUP", "ANY_OF", "N_OF"]


class RequirementChoiceOut(BaseModel):
    """One decision point: pick `choose_count` course(s) from `options`."""

    choice_id: str
    requirement_node_id: int
    kind: RequirementChoiceKind
    label: str
    # Minimum number of courses this requirement asks for. Most COURSE_GROUP
    # requirements state their real size in `required_credit_hours` instead
    # (e.g. "15 credit hours of Gen Ed HASS"), in which case this is 1 and the
    # client should let the student keep picking until the credit target is met.
    choose_count: int
    required_credit_hours: float | None = None
    academic_program_id: int
    program_name: str
    requirement_set_id: int
    requirement_set_name: str
    course_group_id: int | None = None
    total_option_count: int
    options: list[CourseOut]
    # True when `total_option_count` exceeds the inline cap: the client should
    # fetch the full list from `GET /course-groups/{course_group_id}/courses`
    # instead of choosing from the truncated preview.
    options_truncated: bool = False
    # True when the courses already reported as completed cover this choice, so a
    # client can collapse it instead of asking about a settled decision.
    already_satisfied: bool = False
