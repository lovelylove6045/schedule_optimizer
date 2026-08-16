import { useMutation, useQueryClient, type QueryClient } from "@tanstack/react-query"
import { addPlanCourse, movePlanCourse, removePlanCourse, swapPlanCourse } from "@/lib/api/plans"
import type { DegreePlanOut } from "@/lib/types"

interface SwapPlanCourseArgs {
  degreePlanId: number
  planCourseId: number
  newCourseId: number
}

/** Replace one plan board slot's course with an alternative for the same term.
 * On success, updates every cached query holding this plan (its own `/plans/{id}`
 * entry plus its scenario's plan list) so the board reflects the swap immediately
 * without a full refetch. */
export function useSwapPlanCourseMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ degreePlanId, planCourseId, newCourseId }: SwapPlanCourseArgs) =>
      swapPlanCourse(degreePlanId, planCourseId, newCourseId),
    onSuccess: (updatedPlan) => applyUpdatedPlanToCache(queryClient, updatedPlan),
  })
}

interface AddPlanCourseArgs {
  degreePlanId: number
  courseId: number
  termId: number
}

/** Add a brand-new course to a plan in a specific term (an extra elective
 * beyond what the solver assigned). Shares `swapPlanCourse`'s cache-update
 * logic, since both return the same updated-plan shape. */
export function useAddPlanCourseMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ degreePlanId, courseId, termId }: AddPlanCourseArgs) => addPlanCourse(degreePlanId, courseId, termId),
    onSuccess: (updatedPlan) => applyUpdatedPlanToCache(queryClient, updatedPlan),
  })
}

interface RemovePlanCourseArgs {
  degreePlanId: number
  planCourseId: number
}

/** Remove one course entirely from a plan. */
export function useRemovePlanCourseMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ degreePlanId, planCourseId }: RemovePlanCourseArgs) => removePlanCourse(degreePlanId, planCourseId),
    onSuccess: (updatedPlan) => applyUpdatedPlanToCache(queryClient, updatedPlan),
  })
}

interface MovePlanCourseArgs {
  degreePlanId: number
  planCourseId: number
  termId: number
}

/** Move an existing course to another term and update cached plan views. */
export function useMovePlanCourseMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ degreePlanId, planCourseId, termId }: MovePlanCourseArgs) =>
      movePlanCourse(degreePlanId, planCourseId, termId),
    onSuccess: (updatedPlan) => applyUpdatedPlanToCache(queryClient, updatedPlan),
  })
}

/** After any plan-board edit (swap/add/remove), patch every cached query
 * holding this plan so the board reflects it immediately, then lazily
 * refetch the derived views (requirement coverage, comparison metrics) that
 * an edit can shift rather than trying to patch their values by hand. */
function applyUpdatedPlanToCache(queryClient: QueryClient, updatedPlan: DegreePlanOut): void {
  queryClient.setQueryData(["plans", updatedPlan.degree_plan_id], updatedPlan)
  queryClient.setQueriesData(
    { queryKey: ["scenarios", updatedPlan.planning_scenario_id, "plans"] },
    (plans: typeof updatedPlan[] | undefined) =>
      plans?.map((plan) => (plan.degree_plan_id === updatedPlan.degree_plan_id ? updatedPlan : plan)),
  )
  void queryClient.invalidateQueries({ queryKey: ["plans", updatedPlan.degree_plan_id, "requirements"] })
  void queryClient.invalidateQueries({ queryKey: ["plans", "compare"] })
}
