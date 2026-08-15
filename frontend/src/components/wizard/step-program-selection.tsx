import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Combobox, type ComboboxOption } from "@/components/shared/combobox"
import { ErrorState } from "@/components/shared/error-state"
import { LoadingState } from "@/components/shared/loading-state"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { useProgramsQuery } from "@/hooks/use-programs"
import { useTermsQuery } from "@/hooks/use-terms"
import { useScenarioBuilder } from "@/state/scenario-builder-context"

/** Screen 1: choose the primary degree program and a starting term. */
export function StepProgramSelection() {
  const { draft, dispatch } = useScenarioBuilder()
  const programsQuery = useProgramsQuery()
  const termsQuery = useTermsQuery()
  if (programsQuery.isPending || termsQuery.isPending) {
    return <LoadingState label="Loading programs and terms…" />
  }
  if (programsQuery.isError || termsQuery.isError) {
    return <ErrorState message="Couldn't load programs or terms from the server." />
  }
  const programOptions: ComboboxOption[] = programsQuery.data
    .filter((program) => program.program_type === "MAJOR")
    .map((program) => ({
      value: String(program.academic_program_id),
      label: program.program_name,
      description: program.program_code,
    }))
  return (
    <Card>
      <CardHeader>
        <CardTitle>What are you working toward?</CardTitle>
        <CardDescription>Pick your primary major and when you're starting.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="space-y-2">
          <Label htmlFor="student-name">Your name (optional)</Label>
          <Input
            id="student-name"
            placeholder="e.g. Jordan Rivera"
            value={draft.studentDisplayName}
            onChange={(event) => dispatch({ type: "SET_STUDENT_NAME", name: event.target.value })}
          />
        </div>
        <div className="space-y-2">
          <Label>Primary major</Label>
          <Combobox
            options={programOptions}
            value={draft.primaryProgramId === null ? null : String(draft.primaryProgramId)}
            onChange={(value) => dispatch({ type: "SET_PRIMARY_PROGRAM", programId: Number(value) })}
            placeholder="Search for a major…"
            searchPlaceholder="Search majors…"
          />
        </div>
        <div className="grid gap-6 sm:grid-cols-2">
          <div className="space-y-2">
            <Label>Starting term</Label>
            <Select
              value={draft.startTermId === null ? undefined : String(draft.startTermId)}
              onValueChange={(value) => dispatch({ type: "SET_START_TERM", termId: Number(value) })}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Choose a term" />
              </SelectTrigger>
              <SelectContent>
                {termsQuery.data.map((term) => (
                  <SelectItem key={term.term_id} value={String(term.term_id)}>
                    {term.term_code}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Target graduation term (optional)</Label>
            <Select
              value={draft.targetGraduationTermId === null ? undefined : String(draft.targetGraduationTermId)}
              onValueChange={(value) => dispatch({ type: "SET_TARGET_TERM", termId: Number(value) })}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="No specific target" />
              </SelectTrigger>
              <SelectContent>
                {termsQuery.data.map((term) => (
                  <SelectItem key={term.term_id} value={String(term.term_id)}>
                    {term.term_code}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
