import { useEffect, useMemo, useState } from "react"
import { ArrowLeft, ArrowRight, CheckCircle2, Pencil, SkipForward, Sparkles } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { EmptyState } from "@/components/shared/empty-state"
import { ErrorState } from "@/components/shared/error-state"
import { LoadingState } from "@/components/shared/loading-state"
import { RequirementChoiceCard } from "@/components/wizard/requirement-choice-card"
import { useRequirementChoicesQuery } from "@/hooks/use-requirement-choices"
import {
  completedCourseIds,
  selectedProgramIds,
  useScenarioBuilder,
} from "@/state/scenario-builder-context"
import type { RequirementChoiceOut } from "@/lib/types"
import { cn } from "@/lib/utils"

/** Step 5: where a requirement accepts more than one course ("MATH 1214 or
 * MATH 1211", an approved technical-elective list), let the student pick rather
 * than letting the optimizer decide silently. Presented one choice at a time --
 * a wall of cards for every elective at once was overwhelming -- with a summary
 * recap once every choice has been stepped through. Picks become REQUIRE_COURSE
 * `scenario_preferences`; anything left blank stays the optimizer's call. */
export function StepCourseChoices() {
  const { draft, dispatch } = useScenarioBuilder()
  const programIds = useMemo(() => selectedProgramIds(draft), [draft])
  const completedIds = useMemo(() => completedCourseIds(draft), [draft])
  const choicesQuery = useRequirementChoicesQuery(programIds, completedIds)
  const satisfiedCourseIds = useMemo(
    () => [...completedIds, ...Object.values(draft.courseChoices).flat()],
    [completedIds, draft.courseChoices],
  )
  const [index, setIndex] = useState(0)
  const [showSettled, setShowSettled] = useState(false)
  const choiceIdsKey = (choicesQuery.data ?? []).map((choice) => choice.choice_id).join("|")
  useEffect(() => setIndex(0), [choiceIdsKey])
  if (choicesQuery.isPending) return <LoadingState label="Finding the choices in your requirements…" />
  if (choicesQuery.isError) {
    return (
      <ErrorState
        message="Couldn't load the elective choices for your programs."
        onRetry={() => void choicesQuery.refetch()}
      />
    )
  }
  const allChoices = choicesQuery.data
  const settled = allChoices.filter((choice) => choice.already_satisfied)
  const actionable = allChoices.filter((choice) => !choice.already_satisfied)
  const currentIndex = Math.min(index, actionable.length)
  return (
    <Card>
      <CardHeader>
        <CardTitle>Pick your electives</CardTitle>
        <CardDescription>
          Some of your requirements accept more than one course. Go through them one at a time -- anything you
          leave blank is the optimizer's call.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {actionable.length === 0 ? (
          <NoActionableChoices totalSettled={settled.length} />
        ) : (
          <div className="space-y-3">
            <ChoiceStepper choices={actionable} picks={draft.courseChoices} currentIndex={currentIndex} onJump={setIndex} />
            {currentIndex >= actionable.length ? (
              <ChoiceSummary
                choices={actionable}
                picks={draft.courseChoices}
                excludedCourseIds={draft.excludedCourseIds}
                pickedCount={countPicked(actionable, draft.courseChoices)}
                onEdit={setIndex}
              />
            ) : (
              <ActiveChoiceStep
                choice={actionable[currentIndex]}
                selectedCourseIds={draft.courseChoices[actionable[currentIndex].choice_id] ?? []}
                excludedCourseIds={draft.excludedCourseIds}
                satisfiedCourseIds={satisfiedCourseIds}
                stepNumber={currentIndex + 1}
                totalSteps={actionable.length}
                onToggle={(courseId, maxSelections) =>
                  dispatch({
                    type: "TOGGLE_COURSE_CHOICE",
                    choiceId: actionable[currentIndex].choice_id,
                    courseId,
                    maxSelections,
                  })
                }
                onToggleExclude={(courseId) => dispatch({ type: "TOGGLE_COURSE_EXCLUSION", courseId })}
                onClear={() => dispatch({ type: "CLEAR_COURSE_CHOICE", choiceId: actionable[currentIndex].choice_id })}
                onBack={() => setIndex(currentIndex - 1)}
                onNext={() => setIndex(currentIndex + 1)}
              />
            )}
          </div>
        )}
        {settled.length > 0 ? (
          <SettledChoicesDisclosure choices={settled} isOpen={showSettled} onToggle={() => setShowSettled(!showSettled)} />
        ) : null}
      </CardContent>
    </Card>
  )
}

interface ChoiceStepperProps {
  choices: RequirementChoiceOut[]
  picks: Record<string, number[]>
  currentIndex: number
  onJump: (index: number) => void
}

/** Clickable progress bar across the top of the stepwise flow: segments turn gold
 * once a choice is picked, and the current (or, past the end, the recap) segment
 * gets a focus ring. Clicking any segment jumps straight to that choice. */
function ChoiceStepper({ choices, picks, currentIndex, onJump }: ChoiceStepperProps) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>
          {currentIndex >= choices.length ? "Review your choices" : `Choice ${currentIndex + 1} of ${choices.length}`}
        </span>
        <span>{countPicked(choices, picks)} locked in</span>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {choices.map((choice, i) => (
          <button
            key={choice.choice_id}
            type="button"
            onClick={() => onJump(i)}
            aria-label={`Go to choice ${i + 1}: ${choice.label}`}
            aria-current={i === currentIndex}
            className={cn(
              "h-1.5 min-w-6 flex-1 rounded-full transition-colors",
              (picks[choice.choice_id]?.length ?? 0) > 0 ? "bg-gold" : "bg-muted-foreground/25",
              i === currentIndex && "ring-2 ring-ring ring-offset-1 ring-offset-background",
            )}
          />
        ))}
      </div>
    </div>
  )
}

interface ActiveChoiceStepProps {
  choice: RequirementChoiceOut
  selectedCourseIds: number[]
  excludedCourseIds: number[]
  satisfiedCourseIds: number[]
  stepNumber: number
  totalSteps: number
  onToggle: (courseId: number, maxSelections: number) => void
  onToggleExclude: (courseId: number) => void
  onClear: () => void
  onBack: () => void
  onNext: () => void
}

/** The current elective decision, plus local Previous/Skip/Next controls that move
 * through the stepwise flow -- distinct from the wizard's own Back/Next, which
 * move between the 8 main screens. */
function ActiveChoiceStep({
  choice,
  selectedCourseIds,
  excludedCourseIds,
  satisfiedCourseIds,
  stepNumber,
  totalSteps,
  onToggle,
  onToggleExclude,
  onClear,
  onBack,
  onNext,
}: ActiveChoiceStepProps) {
  const hasPick = selectedCourseIds.length > 0
  return (
    <div className="space-y-3">
      <RequirementChoiceCard
        choice={choice}
        selectedCourseIds={selectedCourseIds}
        excludedCourseIds={excludedCourseIds}
        satisfiedCourseIds={satisfiedCourseIds}
        onToggle={onToggle}
        onToggleExclude={onToggleExclude}
        onClear={onClear}
      />
      <div className="flex items-center justify-between gap-2">
        <Button type="button" variant="outline" size="sm" onClick={onBack} disabled={stepNumber === 1}>
          <ArrowLeft className="size-3.5" />
          Previous
        </Button>
        <Button type="button" size="sm" variant={hasPick ? "default" : "outline"} onClick={onNext}>
          {hasPick ? (
            <>
              {stepNumber === totalSteps ? "Finish" : "Next choice"}
              <ArrowRight className="size-3.5" />
            </>
          ) : (
            <>
              <SkipForward className="size-3.5" />
              Skip
            </>
          )}
        </Button>
      </div>
    </div>
  )
}

interface ChoiceSummaryProps {
  choices: RequirementChoiceOut[]
  picks: Record<string, number[]>
  excludedCourseIds: number[]
  pickedCount: number
  onEdit: (index: number) => void
}

/** The recap shown once the student has stepped through every actionable choice:
 * what's locked in, and a one-click way to revisit any of them. */
function ChoiceSummary({ choices, picks, excludedCourseIds, pickedCount, onEdit }: ChoiceSummaryProps) {
  return (
    <div className="glass-inset space-y-3 rounded-xl p-4">
      <div className="flex items-center gap-2.5">
        <CheckCircle2 className="size-5 shrink-0 text-success" aria-hidden="true" />
        <div>
          <p className="text-sm font-semibold">All {choices.length} elective choices reviewed</p>
          <p className="text-xs text-muted-foreground">
            {pickedCount} course{pickedCount === 1 ? "" : "s"} locked in
            {excludedCourseIds.length > 0
              ? `, ${excludedCourseIds.length} excluded`
              : ""}
            ; the rest are left to the optimizer.
          </p>
        </div>
      </div>
      <ul className="space-y-1.5">
        {choices.map((choice, i) => (
          <li key={choice.choice_id} className="flex items-center justify-between gap-2 text-sm">
            <span className="min-w-0 truncate">
              {choice.label} —{" "}
              <span className="text-muted-foreground">
                {pickSummary(choice, picks[choice.choice_id] ?? [], excludedCourseIds)}
              </span>
            </span>
            <Button type="button" variant="ghost" size="sm" className="shrink-0" onClick={() => onEdit(i)}>
              <Pencil className="size-3.5" />
              Change
            </Button>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Describe one choice's outcome for the summary list, by course code when the
 * picked/excluded course is in the preview list, or just a count otherwise (a
 * pick made from an expanded/truncated option list a preview doesn't carry). */
function pickSummary(choice: RequirementChoiceOut, picked: number[], excludedCourseIds: number[]): string {
  const excludedHere = choice.options.filter((course) => excludedCourseIds.includes(course.course_id))
  const exclusionNote = excludedHere.length > 0 ? ` (excluding ${excludedHere.length})` : ""
  if (picked.length === 0) return `left to the optimizer${exclusionNote}`
  const codes = picked
    .map((id) => choice.options.find((course) => course.course_id === id))
    .filter((course): course is NonNullable<typeof course> => course != null)
    .map((course) => `${course.subject_code} ${course.course_number}`)
  const pickedLabel =
    codes.length === picked.length ? codes.join(", ") : `${picked.length} course${picked.length === 1 ? "" : "s"} picked`
  return `${pickedLabel}${exclusionNote}`
}

/** Shown when every requirement in the student's programs names a specific
 * course already, or completed coursework already covers every optional one. */
function NoActionableChoices({ totalSettled }: { totalSettled: number }) {
  return (
    <EmptyState
      icon={Sparkles}
      title={totalSettled > 0 ? "Every choice is already satisfied" : "No elective choices to make"}
      description={
        totalSettled > 0
          ? "Your completed coursework already covers all of these -- nothing left to decide."
          : "Every requirement in your programs names a specific course, so there's nothing to pick here."
      }
    />
  )
}

interface SettledChoicesDisclosureProps {
  choices: RequirementChoiceOut[]
  isOpen: boolean
  onToggle: () => void
}

/** Collapsed-by-default list of choices the student's completed courses already
 * satisfy -- kept out of the stepwise flow since there's nothing left to decide. */
function SettledChoicesDisclosure({ choices, isOpen, onToggle }: SettledChoicesDisclosureProps) {
  return (
    <div className="space-y-2">
      <Button type="button" variant="ghost" size="sm" onClick={onToggle}>
        <CheckCircle2 className="size-3.5 text-success" aria-hidden="true" />
        {isOpen ? "Hide" : "Show"} {choices.length} requirement{choices.length === 1 ? "" : "s"} already covered
      </Button>
      {isOpen ? (
        <ul className="space-y-1.5">
          {choices.map((choice) => (
            <li key={choice.choice_id} className="glass-inset flex items-center justify-between gap-2 rounded-lg p-2.5 text-sm">
              <span className="min-w-0 truncate">{choice.label}</span>
              <Badge className="bg-success text-success-foreground shrink-0">Done</Badge>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}

/** Total courses picked across every choice passed in. */
function countPicked(choices: RequirementChoiceOut[], picks: Record<string, number[]>): number {
  return choices.reduce((total, choice) => total + (picks[choice.choice_id]?.length ?? 0), 0)
}
