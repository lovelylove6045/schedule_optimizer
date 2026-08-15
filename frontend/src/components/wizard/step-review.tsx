import { useMemo } from "react"
import { BookmarkCheck, CalendarRange, GraduationCap, Layers, Sparkles, SlidersHorizontal, Sun } from "lucide-react"
import type { LucideIcon } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { useCollegesQuery } from "@/hooks/use-colleges"
import { useProgramsQuery } from "@/hooks/use-programs"
import { useTermsQuery } from "@/hooks/use-terms"
import { OBJECTIVE_LABELS } from "@/lib/objective-labels"
import { selectedProgramIds, useScenarioBuilder, type WizardDraft } from "@/state/scenario-builder-context"

const ROLE_LABELS: Record<string, string> = {
  SECOND_MAJOR: "Second major",
  MINOR: "Minor",
  EMPHASIS: "Emphasis",
}

/** Step 8: everything the wizard collected, in one place, with a jump-back link per
 * section — so nobody hits "Generate" (a solve that can run up to a few minutes) unsure of what they
 * asked for. */
export function StepReview() {
  const { draft, dispatch } = useScenarioBuilder()
  const programsQuery = useProgramsQuery()
  const termsQuery = useTermsQuery()
  const collegesQuery = useCollegesQuery()
  const programIds = useMemo(() => selectedProgramIds(draft), [draft])
  const programName = (id: number) =>
    programsQuery.data?.find((p) => p.academic_program_id === id)?.program_name ?? `Program #${id}`
  const termCode = (id: number | null) =>
    id === null ? null : (termsQuery.data?.find((t) => t.term_id === id)?.term_code ?? `Term #${id}`)
  const collegeName =
    draft.collegeId === null
      ? "All schools"
      : (collegesQuery.data?.find((c) => c.college_id === draft.collegeId)?.college_name ?? "—")
  const lockedCourseCount = Object.values(draft.courseChoices).flat().length
  const excludedCourseCount = draft.excludedCourseIds.length
  return (
    <Card>
      <CardHeader>
        <CardTitle>Ready to generate</CardTitle>
        <CardDescription>
          Double-check the plan inputs below, then generate. Solving several strategies usually takes under a
          minute, but a tightly-constrained scenario can take a few minutes while the solver keeps searching instead
          of giving up early.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <ReviewRow icon={Layers} label="School" onEdit={() => dispatch({ type: "GO_TO_STEP", step: 1 })}>
          {collegeName}
        </ReviewRow>
        <ReviewRow icon={GraduationCap} label="Primary major" onEdit={() => dispatch({ type: "GO_TO_STEP", step: 2 })}>
          {draft.primaryProgramId === null ? "Not selected" : programName(draft.primaryProgramId)}
        </ReviewRow>
        <ReviewRow icon={CalendarRange} label="Timeline" onEdit={() => dispatch({ type: "GO_TO_STEP", step: 2 })}>
          Starting {termCode(draft.startTermId) ?? "—"}
          {draft.targetGraduationTermId
            ? `, targeting ${termCode(draft.targetGraduationTermId)}`
            : ", no target graduation term"}
        </ReviewRow>
        <ReviewRow
          icon={BookmarkCheck}
          label="Completed coursework"
          onEdit={() => dispatch({ type: "GO_TO_STEP", step: 3 })}
        >
          {draft.completedCourses.length === 0
            ? "Nothing reported — planning from scratch"
            : `${draft.completedCourses.length} course${draft.completedCourses.length === 1 ? "" : "s"} reported`}
        </ReviewRow>
        <ReviewRow icon={Sparkles} label="Additional programs" onEdit={() => dispatch({ type: "GO_TO_STEP", step: 4 })}>
          {draft.additionalPrograms.length === 0 ? (
            "Just the primary major"
          ) : (
            <span className="flex flex-wrap gap-1.5">
              {draft.additionalPrograms.map((program) => (
                <Badge key={program.academicProgramId} variant="secondary">
                  {programName(program.academicProgramId)} · {ROLE_LABELS[program.role] ?? program.role}
                </Badge>
              ))}
            </span>
          )}
        </ReviewRow>
        <ReviewRow icon={Sparkles} label="Elective choices" onEdit={() => dispatch({ type: "GO_TO_STEP", step: 5 })}>
          {lockedCourseCount === 0
            ? "No preferences"
            : `${lockedCourseCount} course${lockedCourseCount === 1 ? "" : "s"} locked in across ${
                Object.keys(draft.courseChoices).filter((key) => draft.courseChoices[key].length > 0).length
              } requirement(s)`}
          {excludedCourseCount > 0 ? `, ${excludedCourseCount} excluded` : ""}
          {lockedCourseCount === 0 && excludedCourseCount === 0 ? " — the optimizer picks every elective" : ""}
        </ReviewRow>
        <ReviewRow icon={SlidersHorizontal} label="Credit load" onEdit={() => dispatch({ type: "GO_TO_STEP", step: 6 })}>
          {draft.defaultMinimumCredits ?? "—"}–{draft.defaultMaximumCredits ?? "—"} credits per term
          {draft.enforceProgramCreditMinimum
            ? ", must reach your major's full published total"
            : ", no full-total requirement"}
        </ReviewRow>
        <ReviewRow icon={Sun} label="Term availability" onEdit={() => dispatch({ type: "GO_TO_STEP", step: 6 })}>
          {draft.allowSummer ? "Summer allowed" : "No summer terms"}
          {draft.excludedTermIds.length > 0
            ? `, ${draft.excludedTermIds.length} term(s) excluded`
            : ", no excluded terms"}
        </ReviewRow>
        <ReviewRow icon={Sparkles} label="Top priority" onEdit={() => dispatch({ type: "GO_TO_STEP", step: 7 })}>
          {OBJECTIVE_LABELS[draft.objectiveOrder[0]].title}
        </ReviewRow>
        {programIds.length === 0 ? (
          <p className="text-sm text-destructive">
            Pick a primary major on step 2 before generating.
          </p>
        ) : null}
      </CardContent>
    </Card>
  )
}

interface ReviewRowProps {
  icon: LucideIcon
  label: string
  onEdit: () => void
  children: React.ReactNode
}

/** One labelled summary line with an inline "Change" jump back to its step. */
function ReviewRow({ icon: Icon, label, onEdit, children }: ReviewRowProps) {
  return (
    <div className="glass-inset flex flex-wrap items-start gap-3 rounded-lg p-3">
      <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
        <Icon className="size-4" aria-hidden="true" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-xs text-muted-foreground">{label}</span>
        <span className="block text-sm font-medium">{children}</span>
      </span>
      <Button variant="ghost" size="sm" onClick={onEdit}>
        Change
      </Button>
    </div>
  )
}

/** Whether the draft has everything `POST /scenarios` requires. */
export function isDraftSubmittable(draft: WizardDraft): boolean {
  return draft.primaryProgramId !== null && draft.startTermId !== null
}
