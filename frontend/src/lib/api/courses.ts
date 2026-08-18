import { apiFetch } from "@/lib/api/client"
import type { CourseOut, PrerequisiteNodeOut } from "@/lib/types"

export interface CourseSearchFilters {
  collegeId?: number | null
  departmentId?: number | null
}

/** Search courses by code/title with optional school filters. */
export function searchCourses(search: string, filters: CourseSearchFilters = {}): Promise<CourseOut[]> {
  return apiFetch<CourseOut[]>("/courses", {
    searchParams: {
      search,
      college_id: filters.collegeId ?? undefined,
      department_id: filters.departmentId ?? undefined,
    },
  })
}

/** Fetch one course's prerequisite/corequisite tree(s) (empty if it has none). */
export function getCoursePrerequisites(courseId: number): Promise<PrerequisiteNodeOut[]> {
  return apiFetch<PrerequisiteNodeOut[]>(`/courses/${courseId}/prerequisites`)
}
