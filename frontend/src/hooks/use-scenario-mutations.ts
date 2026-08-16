import { useMutation, useQueryClient } from "@tanstack/react-query"
import {
  addScenarioProgram,
  createScenario,
  generateAlternativePlans,
  generatePlans,
  generateRecommendedPlan,
} from "@/lib/api/scenarios"
import type { ScenarioProgramIn } from "@/lib/types"

/** Submit a completed wizard draft as a new planning scenario. */
export function useCreateScenarioMutation() {
  return useMutation({ mutationFn: createScenario })
}

/** Run the optimizer for an already-created scenario and persist its plans. */
export function useGeneratePlansMutation() {
  return useMutation({ mutationFn: generatePlans })
}

/** Generate only the recommended plan for immediate display. */
export function useGenerateRecommendedPlanMutation() {
  return useMutation({ mutationFn: generateRecommendedPlan })
}

/** Generate comparison alternatives independently from the primary result. */
export function useGenerateAlternativePlansMutation() {
  return useMutation({ mutationFn: generateAlternativePlans })
}

interface AddScenarioProgramArgs {
  scenarioId: number
  payload: ScenarioProgramIn
}

/** Add a second major/minor/emphasis to an already-created scenario -- e.g.
 * accepting an overlap suggestion after a plan's already been generated.
 * The caller still has to re-run `/generate` for the new program's
 * requirements to actually show up in a plan; this just records the pick. */
export function useAddScenarioProgramMutation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ scenarioId, payload }: AddScenarioProgramArgs) => addScenarioProgram(scenarioId, payload),
    onSuccess: (_, { scenarioId }) => {
      void queryClient.invalidateQueries({ queryKey: ["scenarios", scenarioId, "programs"] })
    },
  })
}
