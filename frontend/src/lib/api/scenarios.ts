import { apiFetch } from "@/lib/api/client"
import type { DegreePlanOut, ScenarioCreate, ScenarioCreateOut } from "@/lib/types"

/** Submit a new planning scenario, returning its id. */
export function createScenario(payload: ScenarioCreate): Promise<ScenarioCreateOut> {
  return apiFetch<ScenarioCreateOut>("/scenarios", { method: "POST", body: payload })
}

/** Run the optimizer for a scenario and persist its resulting plans. */
export function generatePlans(scenarioId: number): Promise<DegreePlanOut[]> {
  return apiFetch<DegreePlanOut[]>(`/scenarios/${scenarioId}/generate`, { method: "POST" })
}

/** Fetch every already-generated plan for a scenario. */
export function listScenarioPlans(scenarioId: number): Promise<DegreePlanOut[]> {
  return apiFetch<DegreePlanOut[]>(`/scenarios/${scenarioId}/plans`)
}
