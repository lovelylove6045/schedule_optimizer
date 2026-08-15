import { useState } from "react"
import { Plus, Target, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Combobox, type ComboboxOption } from "@/components/shared/combobox"
import { EmptyState } from "@/components/shared/empty-state"
import { ErrorState } from "@/components/shared/error-state"
import { LoadingState } from "@/components/shared/loading-state"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { useProgramsQuery } from "@/hooks/use-programs"
import { useScenarioBuilder, type AdditionalProgram } from "@/state/scenario-builder-context"

const ADDITIONAL_ROLE_OPTIONS: { value: AdditionalProgram["role"]; label: string }[] = [
  { value: "SECOND_MAJOR", label: "Second major" },
  { value: "MINOR", label: "Minor" },
  { value: "EMPHASIS", label: "Emphasis" },
]

/** Screen 3: optional second major/minor/emphasis on top of the primary program.
 * Shows every program (not filtered by academic_program_relationships, which
 * has no data loaded yet) excluding ones already selected. */
export function StepAcademicGoals() {
  const { draft, dispatch } = useScenarioBuilder()
  const programsQuery = useProgramsQuery()
  const [pendingProgramId, setPendingProgramId] = useState<string | null>(null)
  const [pendingRole, setPendingRole] = useState<AdditionalProgram["role"]>("MINOR")
  if (programsQuery.isPending) return <LoadingState label="Loading programs…" />
  if (programsQuery.isError) return <ErrorState message="Couldn't load programs from the server." />
  const takenIds = new Set([draft.primaryProgramId, ...draft.additionalPrograms.map((p) => p.academicProgramId)])
  const options: ComboboxOption[] = programsQuery.data
    .filter((program) => !takenIds.has(program.academic_program_id))
    .map((program) => ({
      value: String(program.academic_program_id),
      label: program.program_name,
      description: program.program_code,
    }))
  /** Look up a program's display name by id, falling back to a generic label. */
  const programName = (id: number) =>
    programsQuery.data.find((p) => p.academic_program_id === id)?.program_name ?? `Program #${id}`
  /** Add the pending program/role selection to the draft and reset the picker. */
  function handleAdd() {
    if (pendingProgramId === null) return
    dispatch({
      type: "ADD_ADDITIONAL_PROGRAM",
      program: { academicProgramId: Number(pendingProgramId), role: pendingRole },
    })
    setPendingProgramId(null)
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>Any other goals?</CardTitle>
        <CardDescription>Add a second major, minor, or emphasis you're also pursuing (optional).</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
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
                  onClick={() => dispatch({ type: "REMOVE_ADDITIONAL_PROGRAM", programId: program.academicProgramId })}
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
