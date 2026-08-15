import { apiFetch } from "@/lib/api/client"
import type { CourseOut } from "@/lib/types"

/** Search the catalog for courses matching `search` (e.g. "CS 101" or "calculus"). */
export function searchCourses(search: string): Promise<CourseOut[]> {
  return apiFetch<CourseOut[]>("/courses", { searchParams: { search } })
}
