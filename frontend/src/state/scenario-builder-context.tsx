import { createContext, useContext, useMemo, useReducer, type ReactNode } from "react"
import type { CourseOut, OptimizationObjectiveType, ScenarioProgramRole, StudentCreditIn } from "@/lib/types"

export const WIZARD_STEP_COUNT = 5

export const ALL_OBJECTIVES: OptimizationObjectiveType[] = [
  "EARLIEST_GRADUATION",
  "MIN_ADDITIONAL_CREDITS",
  "MAX_REQUIREMENT_OVERLAP",
  "BALANCED_WORKLOAD",
  "MIN_SUMMER_ENROLLMENT",
]

export interface AdditionalProgram {
  academicProgramId: number
  role: Exclude<ScenarioProgramRole, "PRIMARY_MAJOR">
}

export interface WizardDraft {
  step: number
  studentDisplayName: string
  startTermId: number | null
  targetGraduationTermId: number | null
  primaryProgramId: number | null
  additionalPrograms: AdditionalProgram[]
  completedCourses: StudentCreditIn[]
  /** course_id -> full CourseOut, so screens can render a title/subject for an
   * already-added completed course without re-fetching or re-searching it. */
  courseDetailsById: Record<number, CourseOut>
  defaultMinimumCredits: number | null
  defaultMaximumCredits: number | null
  allowSummer: boolean
  excludedTermIds: number[]
  objectiveOrder: OptimizationObjectiveType[]
}

const initialDraft: WizardDraft = {
  step: 1,
  studentDisplayName: "",
  startTermId: null,
  targetGraduationTermId: null,
  primaryProgramId: null,
  additionalPrograms: [],
  completedCourses: [],
  courseDetailsById: {},
  defaultMinimumCredits: 12,
  defaultMaximumCredits: 18,
  allowSummer: true,
  excludedTermIds: [],
  objectiveOrder: [...ALL_OBJECTIVES],
}

type Action =
  | { type: "GO_TO_STEP"; step: number }
  | { type: "SET_STUDENT_NAME"; name: string }
  | { type: "SET_START_TERM"; termId: number | null }
  | { type: "SET_TARGET_TERM"; termId: number | null }
  | { type: "SET_PRIMARY_PROGRAM"; programId: number | null }
  | { type: "ADD_ADDITIONAL_PROGRAM"; program: AdditionalProgram }
  | { type: "REMOVE_ADDITIONAL_PROGRAM"; programId: number }
  | { type: "ADD_COMPLETED_COURSE"; credit: StudentCreditIn; courseDetail?: CourseOut }
  | { type: "REMOVE_COMPLETED_COURSE"; index: number }
  | { type: "SET_MIN_CREDITS"; value: number | null }
  | { type: "SET_MAX_CREDITS"; value: number | null }
  | { type: "TOGGLE_SUMMER"; allow: boolean }
  | { type: "TOGGLE_EXCLUDED_TERM"; termId: number }
  | { type: "SET_OBJECTIVE_ORDER"; order: OptimizationObjectiveType[] }
  | { type: "RESET" }

/** Apply one wizard action to the draft, returning a new draft (never mutating the input). */
function reducer(draft: WizardDraft, action: Action): WizardDraft {
  switch (action.type) {
    case "GO_TO_STEP":
      return { ...draft, step: action.step }
    case "SET_STUDENT_NAME":
      return { ...draft, studentDisplayName: action.name }
    case "SET_START_TERM":
      return { ...draft, startTermId: action.termId }
    case "SET_TARGET_TERM":
      return { ...draft, targetGraduationTermId: action.termId }
    case "SET_PRIMARY_PROGRAM":
      return { ...draft, primaryProgramId: action.programId }
    case "ADD_ADDITIONAL_PROGRAM":
      return { ...draft, additionalPrograms: [...draft.additionalPrograms, action.program] }
    case "REMOVE_ADDITIONAL_PROGRAM":
      return {
        ...draft,
        additionalPrograms: draft.additionalPrograms.filter((p) => p.academicProgramId !== action.programId),
      }
    case "ADD_COMPLETED_COURSE":
      return {
        ...draft,
        completedCourses: [...draft.completedCourses, action.credit],
        courseDetailsById: action.courseDetail
          ? { ...draft.courseDetailsById, [action.courseDetail.course_id]: action.courseDetail }
          : draft.courseDetailsById,
      }
    case "REMOVE_COMPLETED_COURSE":
      return { ...draft, completedCourses: draft.completedCourses.filter((_, i) => i !== action.index) }
    case "SET_MIN_CREDITS":
      return { ...draft, defaultMinimumCredits: action.value }
    case "SET_MAX_CREDITS":
      return { ...draft, defaultMaximumCredits: action.value }
    case "TOGGLE_SUMMER":
      return { ...draft, allowSummer: action.allow }
    case "TOGGLE_EXCLUDED_TERM":
      return { ...draft, excludedTermIds: toggleMembership(draft.excludedTermIds, action.termId) }
    case "SET_OBJECTIVE_ORDER":
      return { ...draft, objectiveOrder: action.order }
    case "RESET":
      return initialDraft
    default:
      return draft
  }
}

/** Add `id` to `ids` if absent, or remove it if present. */
function toggleMembership(ids: number[], id: number): number[] {
  return ids.includes(id) ? ids.filter((existing) => existing !== id) : [...ids, id]
}

interface ScenarioBuilderContextValue {
  draft: WizardDraft
  dispatch: React.Dispatch<Action>
}

const ScenarioBuilderContext = createContext<ScenarioBuilderContextValue | null>(null)

/** Provide the shared wizard draft (and its dispatcher) to every step under it. */
export function ScenarioBuilderProvider({ children }: { children: ReactNode }) {
  const [draft, dispatch] = useReducer(reducer, initialDraft)
  const value = useMemo(() => ({ draft, dispatch }), [draft])
  return <ScenarioBuilderContext.Provider value={value}>{children}</ScenarioBuilderContext.Provider>
}

/** Read and update the in-progress scenario draft shared across wizard Screens 1-5. */
export function useScenarioBuilder(): ScenarioBuilderContextValue {
  const context = useContext(ScenarioBuilderContext)
  if (context === null) {
    throw new Error("useScenarioBuilder must be used within a ScenarioBuilderProvider")
  }
  return context
}
