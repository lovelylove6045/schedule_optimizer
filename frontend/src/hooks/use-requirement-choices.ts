import { useQuery } from "@tanstack/react-query"
import { getCourseGroupCourses, listRequirementChoices } from "@/lib/api/choices"

/** Fetch the elective decision points for the wizard's course-choice step.
 * Disabled until at least one program is selected, since the endpoint requires
 * `program_ids`. */
export function useRequirementChoicesQuery(programIds: number[], completedCourseIds: number[]) {
  const sortedPrograms = [...programIds].sort((a, b) => a - b)
  const sortedCompleted = [...completedCourseIds].sort((a, b) => a - b)
  return useQuery({
    queryKey: ["requirement-choices", sortedPrograms, sortedCompleted],
    queryFn: () => listRequirementChoices(programIds, completedCourseIds),
    enabled: programIds.length > 0,
    staleTime: 5 * 60 * 1000,
  })
}

/** Lazily fetch a course group's full member list, for a choice whose inline
 * option preview was truncated. Only enabled once the student asks to see them. */
export function useCourseGroupCoursesQuery(courseGroupId: number | null, enabled: boolean) {
  return useQuery({
    queryKey: ["course-groups", courseGroupId, "courses"],
    queryFn: () => getCourseGroupCourses(courseGroupId as number),
    enabled: enabled && courseGroupId !== null,
    staleTime: Infinity,
  })
}
