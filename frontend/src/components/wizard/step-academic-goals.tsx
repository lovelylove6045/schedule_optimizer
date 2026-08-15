import { useState } from "react"
import { Plus, Sparkles, Target, X } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Combobox, type ComboboxOption } from "@/components/shared/combobox"
import { EmptyState } from "@/components/shared/empty-state"
import { ErrorState } from "@/components/shared/error-state"
import { LoadingState } from "@/components/shared/loading-state"
import { OverlapSuggestionCard } from "@/components/shared/overlap-suggestion-card"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { useProgramOverlapSuggestionsQuery, useProgramsQuery } from "@/hooks/use-programs"
import type { ProgramOverlapOut, ProgramType } from "@/lib/types"
import { useScenarioBuilder, type AdditionalProgram } from "@/state/scenario-builder-context"

const ADDITIONAL_ROLE_OPTIONS: { value: AdditionalProgram["role"]; label: string }[] = [
  { value: "SECOND_MAJOR", label: "Second major" },
  { value: "MINOR", label: "Minor" },
  { value: "EMPHASIS", label: "Emphasis" },
]

/** How each additional-program role maps to the catalog's `program_type`, for
 * filtering overlap suggestions to match whatever role is currently selected. */
const PROGRAM_TYPE_FOR_ROLE: Record<AdditionalProgram["role"], ProgramType> = {
  SECOND_MAJOR: "MAJOR",
  MINOR: "MINOR",
  EMPHASIS: "EMPHASIS",
}

const ROLE_PLURAL_LABELS: Record<AdditionalProgram["role"], string> = {
  SECOND_MAJOR: "second majors",
  MINOR: "minors",
  EMPHASIS: "emphases",
}

const SUGGESTION_DISPLAY_LIMIT = 4

/** Step 4: optional second major/minor/emphasis on top of the primary program.
 * Scoped to the school chosen in step 1 by default, with an escape hatch to browse
 * every school. Still not filtered by `academic_program_relationships` (no rows
 * loaded), so the school filter is what keeps the list manageable. */
export function StepAcademicGoals() {
  const { draft, dispatch } = useScenarioBuilder()
  const programsQuery = useProgramsQuery()
  const [pendingProgramId, setPendingProgramId] = useState<string | null>(null)
  const [pendingRole, setPendingRole] = useState<AdditionalProgram["role"]>("MINOR")
  const [showAllSchools, setShowAllSchools] = useState(draft.collegeId === null)
  const overlapQuery = useProgramOverlapSuggestionsQuery(draft.primaryProgramId, PROGRAM_TYPE_FOR_ROLE[pendingRole])
  if (programsQuery.isPending) return <LoadingState label="Loading programs…" />
  if (programsQuery.isError) return <ErrorState message="Couldn't load programs from the server." />
  const takenIds = new Set([draft.primaryProgramId, ...draft.additionalPrograms.map((p) => p.academicProgramId)])
  const available = programsQuery.data.filter(
    (program) =>
      !takenIds.has(program.academic_program_id) &&
      (showAllSchools || draft.collegeId === null || program.college_id === draft.collegeId),
  )
  const options: ComboboxOption[] = available.map((program) => ({
    value: String(program.academic_program_id),
    label: program.program_name,
    description: [program.program_code, program.college_code].filter(Boolean).join(" · "),
  }))
  const suggestions = (overlapQuery.data ?? [])
    .filter((suggestion) => !takenIds.has(suggestion.academic_program_id))
    .slice(0, SUGGESTION_DISPLAY_LIMIT)
  /** Look up a program's display name by id, falling back to a generic label. */
  const programName = (id: number) =>
    programsQuery.data.find((p) => p.academic_program_id === id)?.program_name ?? `Program #${id}`
  /** Add one program under `role` to the draft and toast a confirmation. */
  function addProgram(programId: number, role: AdditionalProgram["role"]) {
    dispatch({ type: "ADD_ADDITIONAL_PROGRAM", program: { academicProgramId: programId, role } })
    toast.success(`Added ${programName(programId)}`, {
      description: "Your elective choices will refresh to include its requirements.",
    })
  }
  /** Add the pending program/role selection from the search picker and reset it. */
  function handleAdd() {
    if (pendingProgramId === null) return
    addProgram(Number(pendingProgramId), pendingRole)
    setPendingProgramId(null)
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>Any other goals?</CardTitle>
        <CardDescription>Add a second major, minor, or emphasis you're also pursuing (optional).</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {suggestions.length > 0 ? (
          <OverlapSuggestions
            rolePlural={ROLE_PLURAL_LABELS[pendingRole]}
            suggestions={suggestions}
            onAdd={(programId) => addProgram(programId, pendingRole)}
          />
        ) : null}
        {draft.collegeId !== null ? (
          <label className="glass-inset flex items-center justify-between gap-3 rounded-lg p-3">
            <span>
              <Label>Look outside my school</Label>
              <span className="block text-xs text-muted-foreground">
                {showAllSchools
                  ? `Showing all ${available.length} programs across every school.`
                  : `Showing ${available.length} programs in your school.`}
              </span>
            </span>
            <Switch checked={showAllSchools} onCheckedChange={setShowAllSchools} />
          </label>
        ) : null}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="flex-1 space-y-1.5">
            <Combobox
              options={options}
              value={pendingProgramId}
              onChange={setPendingProgramId}
              placeholder="Search for a program…"
              searchPlaceholder="Search programs…"
            />
          </div>
          <div className="w-full space-y-1.5 sm:w-44">
            <Select value={pendingRole} onValueChange={(value) => setPendingRole(value as AdditionalProgram["role"])}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ADDITIONAL_ROLE_OPTIONS.map((role) => (
                  <SelectItem key={role.value} value={role.value}>
                    {role.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button type="button" variant="secondary" disabled={pendingProgramId === null} onClick={handleAdd}>
            <Plus className="size-4" />
            Add
          </Button>
        </div>
        {draft.additionalPrograms.length === 0 ? (
          <EmptyState
            icon={Target}
            title="Just the primary major for now"
            description="That's a perfectly valid plan -- add a program above only if you're pursuing more than one."
          />
        ) : (
          <ul className="divide-y rounded-lg border">
            {draft.additionalPrograms.map((program) => (
              <li key={program.academicProgramId} className="flex items-center justify-between gap-3 px-4 py-3">
                <div>
                  <p className="text-sm font-medium">{programName(program.academicProgramId)}</p>
                  <p className="text-xs text-muted-foreground">
                    {ADDITIONAL_ROLE_OPTIONS.find((r) => r.value === program.role)?.label}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Remove"
                  onClick={() => {
                    dispatch({ type: "REMOVE_ADDITIONAL_PROGRAM", programId: program.academicProgramId })
                    toast.info(`Removed ${programName(program.academicProgramId)}`)
                  }}
                >
                  <X className="size-4" />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

interface OverlapSuggestionsProps {
  rolePlural: string
  suggestions: ProgramOverlapOut[]
  onAdd: (programId: number) => void
}

/** The top programs, for the currently-selected role, that reuse most of the
 * primary major's own courses -- so a student can spot a "mostly free" second
 * major/minor/emphasis before searching the full catalog by hand. */
function OverlapSuggestions({ rolePlural, suggestions, onAdd }: OverlapSuggestionsProps) {
  return (
    <div className="glass-inset space-y-3 rounded-xl p-4">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <Sparkles className="size-4 text-gold" aria-hidden="true" />
        Suggested {rolePlural} that overlap with your major
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        {suggestions.map((suggestion) => (
          <OverlapSuggestionCard key={suggestion.academic_program_id} suggestion={suggestion} onAdd={onAdd} />
        ))}
      </div>
    </div>
  )
}
