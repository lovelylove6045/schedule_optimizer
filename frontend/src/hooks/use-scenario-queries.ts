import { useQuery } from "@tanstack/react-query"
import { getScenarioPrograms } from "@/lib/api/scenarios"

/** Fetch every major/minor/emphasis already selected on a scenario -- used on
 * the results page to find the primary program (for overlap suggestions)
 * and which programs are already taken. */
export function useScenarioProgramsQuery(scenarioId: number | undefined) {
  return useQuery({
    queryKey: ["scenarios", scenarioId, "programs"],
    queryFn: () => getScenarioPrograms(scenarioId as number),
    enabled: scenarioId !== undefined,
  })
}
