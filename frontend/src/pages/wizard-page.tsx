import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { ErrorState } from "@/components/shared/error-state"
import { TermRibbon, type TermRibbonItem } from "@/components/layout/term-ribbon"
import { StepProgramSelection } from "@/components/wizard/step-program-selection"
import { StepAcademicProgress } from "@/components/wizard/step-academic-progress"
import { StepAcademicGoals } from "@/components/wizard/step-academic-goals"
import { StepPlanningConstraints } from "@/components/wizard/step-planning-constraints"
import { StepObjectiveSelection } from "@/components/wizard/step-objective-selection"
import { useCreateScenarioMutation, useGeneratePlansMutation } from "@/hooks/use-scenario-mutations"
import { ScenarioBuilderProvider, useScenarioBuilder, WIZARD_STEP_COUNT, type WizardDraft } from "@/state/scenario-builder-context"
import type { ScenarioCreate } from "@/lib/types"

const STEP_LABELS = ["Programs", "Progress", "Goals", "Constraints", "Objectives"]

/** Route entry point for "/": wraps the 5-screen scenario wizard in its own draft context. */
export function WizardPage() {
  return (
    <ScenarioBuilderProvider>
      <WizardContent />
    </ScenarioBuilderProvider>
  )
}

/** Owns the wizard's ribbon, current step's screen, and the final submit flow. */
function WizardContent() {
  const { draft, dispatch } = useScenarioBuilder()
  const navigate = useNavigate()
  const createScenario = useCreateScenarioMutation()
  const generatePlans = useGeneratePlansMutation()
  const [submitError, setSubmitError] = useState<string | null>(null)
  const ribbonItems: TermRibbonItem[] = STEP_LABELS.map((label, index) => ({
    id: index + 1,
    label,
    state: index + 1 < draft.step ? "completed" : index + 1 === draft.step ? "current" : "upcoming",
  }))
  const isSubmitting = createScenario.isPending || generatePlans.isPending
  /** Create the scenario, generate its plans, and navigate to the results page. */
  async function handleSubmit() {
    setSubmitError(null)
    try {
      const { planning_scenario_id } = await createScenario.mutateAsync(buildScenarioPayload(draft))
      const plans = await generatePlans.mutateAsync(planning_scenario_id)
      navigate(`/plans/${planning_scenario_id}`, { state: { plans } })
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "Couldn't generate your plan. Please try again.")
    }
  }
  return (
    <div className="space-y-6">
      <TermRibbon items={ribbonItems} />
      {stepContent(draft.step)}
      {submitError ? <ErrorState message={submitError} onRetry={handleSubmit} /> : null}
      <WizardNavigation
        step={draft.step}
        canProceed={canProceedFromStep(draft.step, draft)}
        isSubmitting={isSubmitting}
        onBack={() => dispatch({ type: "GO_TO_STEP", step: draft.step - 1 })}
        onNext={() => dispatch({ type: "GO_TO_STEP", step: draft.step + 1 })}
        onSubmit={handleSubmit}
      />
    </div>
  )
}

/** Render the screen component for the wizard's current step. */
function stepContent(step: number) {
  switch (step) {
    case 1:
      return <StepProgramSelection />
    case 2:
      return <StepAcademicProgress />
    case 3:
      return <StepAcademicGoals />
    case 4:
      return <StepPlanningConstraints />
    default:
      return <StepObjectiveSelection />
  }
}

/** Return whether the wizard may advance past `step` given the current draft. */
function canProceedFromStep(step: number, draft: { primaryProgramId: number | null; startTermId: number | null }): boolean {
  if (step === 1) return draft.primaryProgramId !== null && draft.startTermId !== null
  return true
}

interface WizardNavigationProps {
  step: number
  canProceed: boolean
  isSubmitting: boolean
  onBack: () => void
  onNext: () => void
  onSubmit: () => void
}

/** Back/Next/Generate button row at the bottom of every wizard step. */
function WizardNavigation({ step, canProceed, isSubmitting, onBack, onNext, onSubmit }: WizardNavigationProps) {
  const isLastStep = step === WIZARD_STEP_COUNT
  return (
    <div className="flex items-center justify-between border-t pt-4">
      <Button type="button" variant="outline" onClick={onBack} disabled={step === 1 || isSubmitting}>
        Back
      </Button>
      {isLastStep ? (
        <Button type="button" onClick={onSubmit} disabled={isSubmitting}>
          {isSubmitting ? <Loader2 className="size-4 animate-spin" /> : null}
          {isSubmitting ? "Generating your plan…" : "Generate my plan"}
        </Button>
      ) : (
        <Button type="button" onClick={onNext} disabled={!canProceed}>
          Next
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
    programs: [
      { academic_program_id: draft.primaryProgramId, program_role: "PRIMARY_MAJOR" },
      ...draft.additionalPrograms.map((program) => ({
        academic_program_id: program.academicProgramId,
        program_role: program.role,
      })),
    ],
    completed_courses: draft.completedCourses,
    term_overrides: draft.excludedTermIds.map((termId) => ({ term_id: termId, is_excluded: true })),
    objectives: draft.objectiveOrder.map((objectiveType, index) => ({
      objective_type: objectiveType,
      weight: 1,
      display_order: index,
    })),
  }
}
