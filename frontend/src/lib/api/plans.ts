import { apiFetch } from "@/lib/api/client"
import type { DegreePlanOut, PlanComparisonOut, RequirementSetOut } from "@/lib/types"

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
