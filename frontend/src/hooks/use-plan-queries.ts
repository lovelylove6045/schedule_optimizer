import { useQuery } from "@tanstack/react-query"
import { comparePlans, getPlanRequirements, getPlanSwapOptions } from "@/lib/api/plans"
import { listScenarioPlans } from "@/lib/api/scenarios"

/** Fetch every persisted plan for a scenario (Screens 6/7's data source on a
 * fresh page load or refresh, when there's no just-generated result in memory). */
export function useScenarioPlansQuery(scenarioId: number | undefined) {
  return useQuery({
    queryKey: ["scenarios", scenarioId, "plans"],
    queryFn: () => listScenarioPlans(scenarioId as number),
    enabled: scenarioId !== undefined,
  })
}

/** Fetch side-by-side comparison metrics for a set of plan ids (Screen 7). */
export function usePlanComparisonQuery(planIds: number[]) {
  return useQuery({
    queryKey: ["plans", "compare", planIds],
    queryFn: () => comparePlans(planIds),
    enabled: planIds.length > 0,
  })
}

/** Fetch one plan's requirement coverage tree (Screen 8). */
export function usePlanRequirementsQuery(degreePlanId: number | undefined) {
  return useQuery({
    queryKey: ["plans", degreePlanId, "requirements"],
    queryFn: () => getPlanRequirements(degreePlanId as number),
    enabled: degreePlanId !== undefined,
  })
}

/** Fetch the plan board's per-course swap alternatives (Screen 6). Keyed by
 * plan_course_id; a course with no listed alternatives can't be swapped. */
export function usePlanSwapOptionsQuery(degreePlanId: number | undefined) {
  return useQuery({
    queryKey: ["plans", degreePlanId, "swap-options"],
    queryFn: () => getPlanSwapOptions(degreePlanId as number),
    enabled: degreePlanId !== undefined,
    staleTime: 5 * 60 * 1000,
  })
}
