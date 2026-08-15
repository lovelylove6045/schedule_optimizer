import { apiFetch } from "@/lib/api/client"
import type { CourseGroupMembersOut, RequirementChoiceOut } from "@/lib/types"

/** Fetch the elective decision points across a set of programs' requirement trees. */
export function listRequirementChoices(
  programIds: number[],
  completedCourseIds: number[] = [],
): Promise<RequirementChoiceOut[]> {
  return apiFetch<RequirementChoiceOut[]>("/requirement-choices", {
    searchParams: {
      program_ids: programIds.join(","),
      completed_course_ids: completedCourseIds.join(","),
    },
  })
}

/** Fetch every course in one course group -- used when a choice's option list came
 * back truncated (`options_truncated`) and the student wants to see all of them. */
export function getCourseGroupCourses(courseGroupId: number): Promise<CourseGroupMembersOut> {
  return apiFetch<CourseGroupMembersOut>(`/course-groups/${courseGroupId}/courses`)
}
