import { useState } from "react"
import { Sparkles, Target, X } from "lucide-react"
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

/** Step 4: choose an additional-goal type, then browse compatible programs by department. */
export function StepAcademicGoals() {
  const { draft, dispatch } = useScenarioBuilder()
  const programsQuery = useProgramsQuery()
  const [pendingRole, setPendingRole] = useState<AdditionalProgram["role"] | null>(null)
  const [departmentId, setDepartmentId] = useState<number | null>(null)
  const overlapQuery = useProgramOverlapSuggestionsQuery(
    draft.primaryProgramId,
    pendingRole === null ? undefined : PROGRAM_TYPE_FOR_ROLE[pendingRole],
  )
  if (programsQuery.isPending) return <LoadingState label="Loading programs…" />
  if (programsQuery.isError) return <ErrorState message="Couldn't load programs from the server." />
  const takenIds = new Set([draft.primaryProgramId, ...draft.additionalPrograms.map((p) => p.academicProgramId)])
  const selectedMajorIds = new Set([
    draft.primaryProgramId,
    ...draft.additionalPrograms
      .filter((program) => program.role === "SECOND_MAJOR")
      .map((program) => program.academicProgramId),
  ])
  const expectedType = pendingRole === null ? null : PROGRAM_TYPE_FOR_ROLE[pendingRole]
  const available = programsQuery.data.filter(
    (program) =>
      !takenIds.has(program.academic_program_id) &&
      expectedType !== null && program.program_type === expectedType &&
      (departmentId === null || program.department_id === departmentId) &&
      (pendingRole !== "EMPHASIS" ||
        program.compatible_parent_program_ids.some((parentId) => selectedMajorIds.has(parentId))),
  )
  const departments = Array.from(
    new Map(
      programsQuery.data
        .filter((program) => expectedType !== null && program.program_type === expectedType)
        .map((program) => [program.department_id, program.department_name ?? program.department_code ?? "Department"]),
    ),
  ).sort((a, b) => a[1].localeCompare(b[1]))
  const options: ComboboxOption[] = available.map((program) => ({
    value: String(program.academic_program_id),
    label: program.program_name,
    description: [program.program_code, program.college_code].filter(Boolean).join(" · "),
  }))
  const suggestions = (overlapQuery.data ?? [])
    .filter((suggestion) => {
      const program = programsQuery.data.find((item) => item.academic_program_id === suggestion.academic_program_id)
      return !takenIds.has(suggestion.academic_program_id) &&
        (pendingRole !== "EMPHASIS" ||
          Boolean(program?.compatible_parent_program_ids.some((parentId) => selectedMajorIds.has(parentId))))
    })
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
  /** Add a program immediately when it is chosen from the search picker. */
  function handleProgramSelect(programId: string) {
    if (pendingRole === null) return
    addProgram(Number(programId), pendingRole)
  }
  /** Remove one selected additional program and confirm the draft change. */
  function removeProgram(programId: number) {
    dispatch({ type: "REMOVE_ADDITIONAL_PROGRAM", programId })
    toast.info(`Removed ${programName(programId)}`)
  }
  return (
    <AcademicGoalsContent
      pendingRole={pendingRole}
      departmentId={departmentId}
      departments={departments}
      options={options}
      suggestions={suggestions}
      selectedPrograms={draft.additionalPrograms}
      programName={programName}
      onRoleChange={(role) => {
        setPendingRole(role)
        setDepartmentId(null)
      }}
      onDepartmentChange={setDepartmentId}
      onProgramSelect={handleProgramSelect}
      onSuggestionAdd={(programId) => pendingRole && addProgram(programId, pendingRole)}
      onRemove={removeProgram}
    />
  )
}

interface AcademicGoalsContentProps {
  pendingRole: AdditionalProgram["role"] | null
  departmentId: number | null
  departments: [number, string][]
  options: ComboboxOption[]
  suggestions: ProgramOverlapOut[]
  selectedPrograms: AdditionalProgram[]
  programName: (id: number) => string
  onRoleChange: (role: AdditionalProgram["role"] | null) => void
  onDepartmentChange: (id: number | null) => void
  onProgramSelect: (id: string) => void
  onSuggestionAdd: (id: number) => void
  onRemove: (id: number) => void
}

/** Compose the additional-goal picker and current selections. */
function AcademicGoalsContent(props: AcademicGoalsContentProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Any other goals?</CardTitle>
        <CardDescription>Add a second major, minor, or emphasis you're also pursuing (optional).</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <AdditionalGoalPicker {...props} />
        <SelectedAdditionalGoals {...props} />
      </CardContent>
    </Card>
  )
}

/** Let the student choose a role, department, and compatible program. */
function AdditionalGoalPicker(props: AcademicGoalsContentProps) {
  const role = props.pendingRole
  return (
    <>
      {role !== null && props.suggestions.length > 0 ? (
        <OverlapSuggestions rolePlural={ROLE_PLURAL_LABELS[role]} suggestions={props.suggestions} onAdd={props.onSuggestionAdd} />
      ) : null}
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label>Would you like to add another academic goal?</Label>
          <Select value={role ?? "NONE"} onValueChange={(value) => props.onRoleChange(value === "NONE" ? null : value as AdditionalProgram["role"])}>
            <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="NONE">No additional program</SelectItem>
              {ADDITIONAL_ROLE_OPTIONS.map((option) => <SelectItem key={option.value} value={option.value}>Add a {option.label.toLowerCase()}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        {role !== null && role !== "EMPHASIS" ? (
          <div className="space-y-1.5">
            <Label>Department</Label>
            <Select value={props.departmentId === null ? "ALL" : String(props.departmentId)} onValueChange={(value) => props.onDepartmentChange(value === "ALL" ? null : Number(value))}>
              <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="ALL">All departments</SelectItem>
                {props.departments.map(([id, name]) => <SelectItem key={id} value={String(id)}>{name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        ) : role === "EMPHASIS" ? <div className="rounded-lg border bg-muted/30 p-3 text-xs text-muted-foreground">Only emphases attached to your selected major are shown.</div> : <div />}
      </div>
      {role !== null ? (
        <div className="space-y-1.5">
          <Label>{ADDITIONAL_ROLE_OPTIONS.find((option) => option.value === role)?.label}</Label>
          <Combobox options={props.options} value={null} onChange={props.onProgramSelect} placeholder={`Search and add ${ROLE_PLURAL_LABELS[role]}…`} searchPlaceholder={`Search ${ROLE_PLURAL_LABELS[role]}…`} />
          <p className="text-xs text-muted-foreground">Choose a program to add it immediately.</p>
        </div>
      ) : null}
    </>
  )
}

/** Show selected additional programs with an explicit remove action. */
function SelectedAdditionalGoals(props: AcademicGoalsContentProps) {
  if (props.selectedPrograms.length === 0) {
    return <EmptyState icon={Target} title="Just the primary major for now" description="That's a perfectly valid plan -- add a program above only if you're pursuing more than one." />
  }
  return (
    <ul className="divide-y rounded-lg border">
      {props.selectedPrograms.map((program) => (
        <li key={program.academicProgramId} className="flex items-center justify-between gap-3 px-4 py-3">
          <div>
            <p className="text-sm font-medium">{props.programName(program.academicProgramId)}</p>
            <p className="text-xs text-muted-foreground">{ADDITIONAL_ROLE_OPTIONS.find((option) => option.value === program.role)?.label}</p>
          </div>
          <Button variant="ghost" size="icon-sm" aria-label="Remove" onClick={() => props.onRemove(program.academicProgramId)}><X className="size-4" /></Button>
        </li>
      ))}
    </ul>
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
