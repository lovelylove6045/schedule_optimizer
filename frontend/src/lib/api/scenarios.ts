import { apiFetch } from "@/lib/api/client"
import type { DegreePlanOut, OptimizationObjectiveType, ScenarioCreate, ScenarioCreateOut, ScenarioProgramIn, ScenarioProgramOut } from "@/lib/types"

/** Submit a new planning scenario, returning its id. */
export function createScenario(payload: ScenarioCreate, signal?: AbortSignal): Promise<ScenarioCreateOut> {
  return apiFetch<ScenarioCreateOut>("/scenarios", { method: "POST", body: payload, signal })
}

/** Run the optimizer for a scenario and persist its resulting plans. */
export function generatePlans(scenarioId: number): Promise<DegreePlanOut[]> {
  return apiFetch<DegreePlanOut[]>(`/scenarios/${scenarioId}/generate`, { method: "POST" })
}

/** Generate the lexicographic recommended plan without waiting for alternatives. */
export function generateRecommendedPlan(scenarioId: number, signal?: AbortSignal): Promise<DegreePlanOut> {
  return apiFetch<DegreePlanOut>(`/scenarios/${scenarioId}/generate/recommended`, { method: "POST", signal })
}

/** Stop an active recommended-plan solver for a scenario. */
export function cancelPlanGeneration(scenarioId: number): Promise<{ cancelled: boolean }> {
  return apiFetch<{ cancelled: boolean }>(`/scenarios/${scenarioId}/generate/cancel`, { method: "POST" })
}

/** Generate independent alternatives after the recommended plan is usable. */
export function generateAlternativePlans(scenarioId: number, objectiveTypes: OptimizationObjectiveType[]): Promise<DegreePlanOut[]> {
  return apiFetch<DegreePlanOut[]>(`/scenarios/${scenarioId}/generate/alternatives`, {
    method: "POST",
    body: { objective_types: objectiveTypes },
  })
}

/** Fetch every already-generated plan for a scenario. */
export function listScenarioPlans(scenarioId: number): Promise<DegreePlanOut[]> {
  return apiFetch<DegreePlanOut[]>(`/scenarios/${scenarioId}/plans`)
}

/** Fetch every program (major/minor/emphasis) already selected on a scenario. */
export function getScenarioPrograms(scenarioId: number): Promise<ScenarioProgramOut[]> {
  return apiFetch<ScenarioProgramOut[]>(`/scenarios/${scenarioId}/programs`)
}

/** Add a second major/minor/emphasis to an already-created scenario -- e.g.
 * accepting an overlap suggestion after a plan's already been generated. */
export function addScenarioProgram(scenarioId: number, payload: ScenarioProgramIn): Promise<ScenarioProgramOut> {
  return apiFetch<ScenarioProgramOut>(`/scenarios/${scenarioId}/programs`, { method: "POST", body: payload })
}
