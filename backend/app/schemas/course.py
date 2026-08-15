from pydantic import BaseModel, ConfigDict


class CourseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    course_id: int
    subject_id: int
    subject_code: str
    course_number: str
    course_title: str
    credit_hours: float
    course_level: int
    fall_offered: bool
    spring_offered: bool
    summer_offered: bool
    course_type: str


class CourseGroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    course_group_id: int
    course_group_code: str
    course_group_name: str
    course_group_type: str
    description: str | None = None


class CourseGroupMembersOut(BaseModel):
    course_group: CourseGroupOut
    courses: list[CourseOut]
