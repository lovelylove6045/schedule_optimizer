import { apiFetch } from "@/lib/api/client"
import type { CourseOut, PrerequisiteNodeOut } from "@/lib/types"

/** Search the catalog for courses matching `search` (e.g. "CS 101" or "calculus"). */
export function searchCourses(search: string): Promise<CourseOut[]> {
  return apiFetch<CourseOut[]>("/courses", { searchParams: { search } })
}

/** Fetch one course's prerequisite/corequisite tree(s) (empty if it has none). */
export function getCoursePrerequisites(courseId: number): Promise<PrerequisiteNodeOut[]> {
  return apiFetch<PrerequisiteNodeOut[]>(`/courses/${courseId}/prerequisites`)
}
