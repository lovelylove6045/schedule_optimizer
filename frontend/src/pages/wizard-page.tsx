import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { ArrowLeft, ArrowRight, Loader2, Sparkles } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { ErrorState } from "@/components/shared/error-state"
import { TermRibbon, type TermRibbonItem } from "@/components/layout/term-ribbon"
import { StepSchoolSelection } from "@/components/wizard/step-school-selection"
import { StepProgramSelection } from "@/components/wizard/step-program-selection"
import { StepAcademicProgress } from "@/components/wizard/step-academic-progress"
import { StepAcademicGoals } from "@/components/wizard/step-academic-goals"
import { StepCourseChoices } from "@/components/wizard/step-course-choices"
import { StepPlanningConstraints } from "@/components/wizard/step-planning-constraints"
import { StepObjectiveSelection } from "@/components/wizard/step-objective-selection"
import { StepReview, isDraftSubmittable } from "@/components/wizard/step-review"
import { useCreateScenarioMutation, useGenerateRecommendedPlanMutation } from "@/hooks/use-scenario-mutations"
import {
  ScenarioBuilderProvider,
  WIZARD_STEPS,
  WIZARD_STEP_COUNT,
  useScenarioBuilder,
  type WizardDraft,
} from "@/state/scenario-builder-context"
import type { ScenarioCreate, ScenarioPreferenceIn } from "@/lib/types"
import { CatalogSnapshotNotice } from "@/components/catalog/catalog-snapshot-notice"

/** Route entry point for "/": wraps the 8-step scenario wizard in its own draft context. */
export function WizardPage() {
  return (
    <ScenarioBuilderProvider>
      <WizardContent />
    </ScenarioBuilderProvider>
  )
}

/** Owns the wizard's progress chrome, the current step's screen, and the submit flow. */
function WizardContent() {
  const { draft, dispatch } = useScenarioBuilder()
  const navigate = useNavigate()
  const createScenario = useCreateScenarioMutation()
  const generateRecommendedPlan = useGenerateRecommendedPlanMutation()
  const [submitError, setSubmitError] = useState<string | null>(null)
  const ribbonItems: TermRibbonItem[] = WIZARD_STEPS.map(({ step, label }) => ({
    id: step,
    label,
    state: step < draft.step ? "completed" : step === draft.step ? "current" : "upcoming",
  }))
  const isSubmitting = createScenario.isPending || generateRecommendedPlan.isPending
  const blockingReason = blockingReasonForStep(draft)

  /** Create the scenario, generate its plans, and navigate to the results page. */
  async function handleSubmit() {
    setSubmitError(null)
    const progressToast = toast.loading("Optimizing your degree plan…", {
      description: "Solving several strategies — usually under a minute, occasionally a few minutes for a tight scenario.",
    })
    try {
      const { planning_scenario_id } = await createScenario.mutateAsync(buildScenarioPayload(draft))
      const recommendedPlan = await generateRecommendedPlan.mutateAsync(planning_scenario_id)
      const plans = [recommendedPlan]
      const feasible = plans.filter((plan) => plan.status !== "INFEASIBLE")
      if (feasible.length === 0) {
        toast.warning("No plan fits those constraints", {
          id: progressToast,
          description: "Open the results to see which constraint blocked it and what to relax.",
        })
      } else {
        toast.success("Recommended plan ready", {
          id: progressToast,
          description: "You can use it now while alternatives generate separately.",
        })
      }
      navigate(`/plans/${planning_scenario_id}`, { state: { plans } })
    } catch (error) {
      const message = error instanceof Error ? error.message : "Couldn't generate your plan. Please try again."
      toast.error("Couldn't generate your plan", { id: progressToast, description: message })
      setSubmitError(message)
    }
  }

  /** Advance a step, refusing (with an explanation) when the step isn't complete. */
  function handleNext() {
    if (blockingReason !== null) {
      toast.warning(blockingReason)
      return
    }
    dispatch({ type: "GO_TO_STEP", step: draft.step + 1 })
  }

  return (
    <div className="space-y-6">
      <WizardHeader step={draft.step} />
      <CatalogSnapshotNotice />
      <TermRibbon items={ribbonItems} />
      {stepContent(draft.step)}
      {submitError ? <ErrorState message={submitError} onRetry={handleSubmit} /> : null}
      <WizardNavigation
        step={draft.step}
        blockingReason={blockingReason}
        canSubmit={isDraftSubmittable(draft)}
        isSubmitting={isSubmitting}
        onBack={() => dispatch({ type: "GO_TO_STEP", step: draft.step - 1 })}
        onNext={handleNext}
        onSubmit={handleSubmit}
      />
    </div>
  )
}

/** "Step N of 8" caption plus a thin progress bar, so the wizard's length is never a surprise. */
function WizardHeader({ step }: { step: number }) {
  const current = WIZARD_STEPS[step - 1]
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-xl font-extrabold tracking-tight sm:text-2xl">{current.title}</h1>
        <p className="font-mono text-xs text-muted-foreground">
          Step {step} of {WIZARD_STEP_COUNT}
        </p>
      </div>
      <Progress value={(step / WIZARD_STEP_COUNT) * 100} className="h-1.5" />
    </div>
  )
}

/** Render the screen component for the wizard's current step. */
function stepContent(step: number) {
  switch (step) {
    case 1:
      return <StepSchoolSelection />
    case 2:
      return <StepProgramSelection />
    case 3:
      return <StepAcademicProgress />
    case 4:
      return <StepAcademicGoals />
    case 5:
      return <StepCourseChoices />
    case 6:
      return <StepPlanningConstraints />
    case 7:
      return <StepObjectiveSelection />
    default:
      return <StepReview />
  }
}

/** Return why the wizard can't advance past the current step, or null if it can.
 * Returning the reason (rather than a bare boolean) lets the Next button explain
 * itself in a toast instead of just sitting there disabled. */
function blockingReasonForStep(draft: WizardDraft): string | null {
  if (draft.step === 2) {
    if (draft.primaryProgramId === null) return "Choose a primary major to continue."
    if (draft.startTermId === null) return "Choose the term your plan starts in."
  }
  if (draft.step === 6 && creditRangeIsInverted(draft)) {
    return "Your minimum credits per term is higher than your maximum."
  }
  return null
}

/** Whether the credit-load sliders were dragged into an impossible range, which the
 * solver would otherwise report as a bare "infeasible". */
function creditRangeIsInverted(draft: WizardDraft): boolean {
  return (
    draft.defaultMinimumCredits !== null &&
    draft.defaultMaximumCredits !== null &&
    draft.defaultMinimumCredits > draft.defaultMaximumCredits
  )
}

interface WizardNavigationProps {
  step: number
  blockingReason: string | null
  canSubmit: boolean
  isSubmitting: boolean
  onBack: () => void
  onNext: () => void
  onSubmit: () => void
}

/** Sticky Back/Next/Generate bar at the bottom of every wizard step. */
function WizardNavigation({
  step,
  blockingReason,
  canSubmit,
  isSubmitting,
  onBack,
  onNext,
  onSubmit,
}: WizardNavigationProps) {
  const isLastStep = step === WIZARD_STEP_COUNT
  return (
    <div className="glass-panel sticky bottom-4 flex items-center justify-between gap-3 rounded-xl p-3">
      <Button type="button" variant="outline" onClick={onBack} disabled={step === 1 || isSubmitting}>
        <ArrowLeft className="size-4" />
        Back
      </Button>
      {blockingReason !== null && !isLastStep ? (
        <p className="hidden text-xs text-muted-foreground sm:block">{blockingReason}</p>
      ) : null}
      {isLastStep ? (
        <Button type="button" onClick={onSubmit} disabled={isSubmitting || !canSubmit}>
          {isSubmitting ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
          {isSubmitting ? "Generating your plan…" : "Generate my plan"}
        </Button>
      ) : (
        <Button type="button" onClick={onNext} aria-disabled={blockingReason !== null}>
          Next
          <ArrowRight className="size-4" />
        </Button>
      )}
    </div>
  )
}

/** Convert the wizard draft into the ScenarioCreate body POST /scenarios expects. */
function buildScenarioPayload(draft: WizardDraft): ScenarioCreate {
  if (draft.primaryProgramId === null || draft.startTermId === null) {
    throw new Error("A primary program and starting term are required.")
  }
  return {
    student_display_name: draft.studentDisplayName.trim() || undefined,
    start_term_id: draft.startTermId,
    target_graduation_term_id: draft.targetGraduationTermId ?? undefined,
    default_minimum_credits: draft.defaultMinimumCredits ?? undefined,
    default_maximum_credits: draft.defaultMaximumCredits ?? undefined,
    allow_summer: draft.allowSummer,
    summer_maximum_credits: draft.summerMaximumCredits,
    enforce_program_credit_minimum: draft.enforceProgramCreditMinimum,
    programs: [
      { academic_program_id: draft.primaryProgramId, program_role: "PRIMARY_MAJOR" },
      ...draft.additionalPrograms.map((program) => ({
        academic_program_id: program.academicProgramId,
        program_role: program.role,
      })),
    ],
    completed_courses: draft.completedCourses,
    term_overrides: draft.excludedTermIds.map((termId) => ({ term_id: termId, is_excluded: true })),
    preferences: buildCoursePreferences(draft),
    objectives: draft.objectiveOrder.map((objectiveType, index) => ({
      objective_type: objectiveType,
      weight: 1,
      display_order: index,
    })),
  }
}

/** Turn step 5's elective picks and exclusions into REQUIRE_COURSE / AVOID_COURSE
 * preferences, which `optimizer_model._add_hard_preference_constraints` enforces
 * as hard constraints (require this course; never assign that one). */
function buildCoursePreferences(draft: WizardDraft): ScenarioPreferenceIn[] {
  const requiredIds = new Set(Object.values(draft.courseChoices).flat())
  const required: ScenarioPreferenceIn[] = [...requiredIds].map((courseId) => ({
    preference_type: "REQUIRE_COURSE",
    course_id: courseId,
  }))
  const avoided: ScenarioPreferenceIn[] = draft.excludedCourseIds.map((courseId) => ({
    preference_type: "AVOID_COURSE",
    course_id: courseId,
  }))
  return [...required, ...avoided]
}
