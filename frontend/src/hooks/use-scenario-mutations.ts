import { useMutation } from "@tanstack/react-query"
import { createScenario, generatePlans } from "@/lib/api/scenarios"

/** Submit a completed wizard draft as a new planning scenario. */
export function useCreateScenarioMutation() {
  return useMutation({ mutationFn: createScenario })
}

/** Run the optimizer for an already-created scenario and persist its plans. */
export function useGeneratePlansMutation() {
  return useMutation({ mutationFn: generatePlans })
}
