import { Sparkles } from "lucide-react"
import { toast } from "sonner"
import { OverlapSuggestionCard } from "@/components/shared/overlap-suggestion-card"
import { useProgramOverlapSuggestionsQuery } from "@/hooks/use-programs"
import { useAddScenarioProgramMutation } from "@/hooks/use-scenario-mutations"
import { useScenarioProgramsQuery } from "@/hooks/use-scenario-queries"
import type { DegreePlanOut, ProgramOverlapOut, ScenarioProgramRole } from "@/lib/types"

const SUGGESTION_DISPLAY_LIMIT = 3

interface PlanOverlapSuggestionsProps {
  scenarioId: number
  onRegenerate: () => Promise<DegreePlanOut[]>
}

/** Post-generation (and still visible post-swap, since it isn't scoped to any
 * one tab) "suggested minors/second majors that overlap with your major"
 * panel on the results page -- the same idea as the wizard's Screen 4
 * suggestions, but for a student who's already generated a plan and wants to
 * see what else is mostly "free" given their primary major's own courses.
 * Accepting one adds it to the scenario and re-runs the optimizer. */
export function PlanOverlapSuggestions({ scenarioId, onRegenerate }: PlanOverlapSuggestionsProps) {
  const programsQuery = useScenarioProgramsQuery(scenarioId)
  const addProgram = useAddScenarioProgramMutation()
  const programs = programsQuery.data ?? []
  const primaryProgramId = programs.find((program) => program.program_role === "PRIMARY_MAJOR")?.academic_program_id ?? null
  const takenIds = new Set(programs.map((program) => program.academic_program_id))
  const minorSuggestions = visibleSuggestions(useProgramOverlapSuggestionsQuery(primaryProgramId, "MINOR").data, takenIds)
  const majorSuggestions = visibleSuggestions(useProgramOverlapSuggestionsQuery(primaryProgramId, "MAJOR").data, takenIds)
  if (primaryProgramId === null || (minorSuggestions.length === 0 && majorSuggestions.length === 0)) return null

  async function handleAdd(suggestion: ProgramOverlapOut, role: ScenarioProgramRole) {
    const pending = toast.loading(`Adding ${suggestion.program_name}…`)
    try {
      await addProgram.mutateAsync({
        scenarioId,
        payload: { academic_program_id: suggestion.academic_program_id, program_role: role },
      })
      await onRegenerate()
      toast.success(`Added ${suggestion.program_name}`, {
        id: pending,
        description: "Regenerated your plans to include its requirements.",
      })
    } catch (error) {
      toast.error(`Couldn't add ${suggestion.program_name}`, {
        id: pending,
        description: error instanceof Error ? error.message : undefined,
      })
    }
  }

  return (
    <div className="glass-inset space-y-4 rounded-xl p-4">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <Sparkles className="size-4 text-gold" aria-hidden="true" />
        More overlap with your major?
      </div>
      <SuggestionGroup
        label="Suggested minors"
        suggestions={minorSuggestions}
        role="MINOR"
        isAdding={addProgram.isPending}
        onAdd={handleAdd}
      />
      <SuggestionGroup
        label="Suggested second majors"
        suggestions={majorSuggestions}
        role="SECOND_MAJOR"
        isAdding={addProgram.isPending}
        onAdd={handleAdd}
      />
    </div>
  )
}

/** Trim an overlap-suggestions result to the programs not already on the
 * scenario, capped at the display limit. */
function visibleSuggestions(suggestions: ProgramOverlapOut[] | undefined, takenIds: Set<number>): ProgramOverlapOut[] {
  return (suggestions ?? [])
    .filter((suggestion) => !takenIds.has(suggestion.academic_program_id))
    .slice(0, SUGGESTION_DISPLAY_LIMIT)
}

interface SuggestionGroupProps {
  label: string
  suggestions: ProgramOverlapOut[]
  role: ScenarioProgramRole
  isAdding: boolean
  onAdd: (suggestion: ProgramOverlapOut, role: ScenarioProgramRole) => void
}

/** One labeled row of overlap suggestion cards for a single program role, or
 * nothing if this scenario has none to show for that role. */
function SuggestionGroup({ label, suggestions, role, isAdding, onAdd }: SuggestionGroupProps) {
  if (suggestions.length === 0) return null
  return (
    <div className="space-y-2">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <div className="grid gap-2 sm:grid-cols-3">
        {suggestions.map((suggestion) => (
          <OverlapSuggestionCard
            key={suggestion.academic_program_id}
            suggestion={suggestion}
            isAdding={isAdding}
            onAdd={() => onAdd(suggestion, role)}
          />
        ))}
      </div>
    </div>
  )
}
