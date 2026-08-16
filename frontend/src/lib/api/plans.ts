import { apiFetch } from "@/lib/api/client"
import type { CourseOut, DegreePlanOut, PlanComparisonOut, RequirementSetOut } from "@/lib/types"

/** Fetch one plan's full semester-by-semester breakdown and messages. */
export function getPlan(degreePlanId: number): Promise<DegreePlanOut> {
  return apiFetch<DegreePlanOut>(`/plans/${degreePlanId}`)
}

/** Fetch side-by-side comparison metrics for a set of plan ids. */
export function comparePlans(planIds: number[]): Promise<PlanComparisonOut> {
  return apiFetch<PlanComparisonOut>("/plans/compare", { searchParams: { ids: planIds.join(",") } })
}

/** Fetch one plan's requirement coverage tree (satisfied/remaining/shared). */
export function getPlanRequirements(degreePlanId: number): Promise<RequirementSetOut[]> {
  return apiFetch<RequirementSetOut[]>(`/plans/${degreePlanId}/requirements`)
}

/** Fetch, per plan_course_id, the alternative courses the plan board can offer
 * for that term slot -- empty for a course whose requirement names no alternative. */
export function getPlanSwapOptions(degreePlanId: number): Promise<Record<number, CourseOut[]>> {
  return apiFetch<Record<number, CourseOut[]>>(`/plans/${degreePlanId}/swap-options`)
}

/** Replace one plan_courses row's assigned course with an alternative, keeping
 * its term, and return the plan with its updated courses/credit totals. */
export function swapPlanCourse(
  degreePlanId: number, planCourseId: number, newCourseId: number
): Promise<DegreePlanOut> {
  return apiFetch<DegreePlanOut>(`/plans/${degreePlanId}/courses/${planCourseId}/swap`, {
    method: "POST",
    body: { new_course_id: newCourseId },
  })
}

/** Add a brand-new course to a plan in a specific term (an extra elective
 * beyond what the solver assigned), returning the plan with updated courses/
 * credit totals. */
export function addPlanCourse(degreePlanId: number, courseId: number, termId: number): Promise<DegreePlanOut> {
  return apiFetch<DegreePlanOut>(`/plans/${degreePlanId}/courses`, {
    method: "POST",
    body: { course_id: courseId, term_id: termId },
  })
}

/** Remove one course entirely from a plan, returning the plan with updated
 * courses/credit totals. */
export function removePlanCourse(degreePlanId: number, planCourseId: number): Promise<DegreePlanOut> {
  return apiFetch<DegreePlanOut>(`/plans/${degreePlanId}/courses/${planCourseId}`, { method: "DELETE" })
}

/** Move an existing course to another term and return the revalidated plan. */
export function movePlanCourse(degreePlanId: number, planCourseId: number, termId: number): Promise<DegreePlanOut> {
  return apiFetch<DegreePlanOut>(`/plans/${degreePlanId}/courses/${planCourseId}/move`, {
    method: "POST",
    body: { term_id: termId },
  })
}
