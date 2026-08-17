import { createContext, useContext, useMemo, useReducer, type ReactNode } from "react"
import type { CourseOut, OptimizationObjectiveType, ScenarioProgramRole, StudentCreditIn } from "@/lib/types"

/**
 * The wizard is deliberately fine-grained: 8 short screens rather than a few
 * dense ones, so a student is never asked more than one kind of question at a
 * time. Step 1 (school) narrows the 147-program catalog before the program
 * picker opens, and step 5 (course choices) is where the student -- not the
 * solver -- decides between interchangeable courses.
 */
export const WIZARD_STEPS = [
  { step: 1, label: "School", title: "Which school are you in?" },
  { step: 2, label: "Program", title: "What are you working toward?" },
  { step: 3, label: "Progress", title: "What have you already completed?" },
  { step: 4, label: "Goals", title: "Any other goals?" },
  { step: 5, label: "Courses", title: "Pick your electives" },
  { step: 6, label: "Limits", title: "How much can you take on?" },
  { step: 7, label: "Priority", title: "What matters most to you?" },
  { step: 8, label: "Review", title: "Ready to generate" },
] as const

export const WIZARD_STEP_COUNT = WIZARD_STEPS.length

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
  /** Narrows the program pickers on steps 2 and 4; null means "all schools". */
  collegeId: number | null
  startTermId: number | null
  targetGraduationTermId: number | null
  primaryProgramId: number | null
  additionalPrograms: AdditionalProgram[]
  completedCourses: StudentCreditIn[]
  /** course_id -> full CourseOut, so screens can render a title/subject for an
   * already-added completed course without re-fetching or re-searching it. */
  courseDetailsById: Record<number, CourseOut>
  /** Step 5's answers: requirement choice_id -> the course_ids the student picked.
   * Submitted as REQUIRE_COURSE `scenario_preferences`, which the solver enforces. */
  courseChoices: Record<string, number[]>
  /** Step 5's exclusions: course_ids the student never wants assigned (e.g. "I'm
   * weak at math, don't put me in MATH 3213 even if it's a valid elective option").
   * Submitted as AVOID_COURSE `scenario_preferences`, enforced as a hard constraint
   * the same way REQUIRE_COURSE is -- just forbidding instead of requiring. Course-level
   * rather than per-choice, since a course excluded here should stay excluded
   * everywhere it might otherwise show up as an option. */
  excludedCourseIds: number[]
  defaultMinimumCredits: number | null
  defaultMaximumCredits: number | null
  allowSummer: boolean
  summerMaximumCredits: number
  /** Forces the generated plan to reach the primary major's (and any second
   * major's) officially published total_credit_hours, not just its named
   * requirements -- on by default; a student can turn it off if it makes
   * their scenario infeasible (see backend: enforce_program_credit_minimum). */
  enforceProgramCreditMinimum: boolean
  excludedTermIds: number[]
  objectiveOrder: OptimizationObjectiveType[]
}

const initialDraft: WizardDraft = {
  step: 1,
  studentDisplayName: "",
  collegeId: null,
  startTermId: null,
  targetGraduationTermId: null,
  primaryProgramId: null,
  additionalPrograms: [],
  completedCourses: [],
  courseDetailsById: {},
  courseChoices: {},
  excludedCourseIds: [],
  defaultMinimumCredits: 12,
  defaultMaximumCredits: 18,
  allowSummer: false,
  summerMaximumCredits: 9,
  enforceProgramCreditMinimum: true,
  excludedTermIds: [],
  objectiveOrder: ["EARLIEST_GRADUATION", "BALANCED_WORKLOAD", "MIN_ADDITIONAL_CREDITS"],
}

type Action =
  | { type: "GO_TO_STEP"; step: number }
  | { type: "SET_STUDENT_NAME"; name: string }
  | { type: "SET_COLLEGE"; collegeId: number | null }
  | { type: "SET_START_TERM"; termId: number | null }
  | { type: "SET_TARGET_TERM"; termId: number | null }
  | { type: "SET_PRIMARY_PROGRAM"; programId: number | null }
  | { type: "ADD_ADDITIONAL_PROGRAM"; program: AdditionalProgram }
  | { type: "REMOVE_ADDITIONAL_PROGRAM"; programId: number }
  | { type: "ADD_COMPLETED_COURSE"; credit: StudentCreditIn; courseDetail?: CourseOut }
  | { type: "REMOVE_COMPLETED_COURSE"; index: number }
  | { type: "TOGGLE_COURSE_CHOICE"; choiceId: string; courseId: number; maxSelections: number }
  | { type: "CLEAR_COURSE_CHOICE"; choiceId: string }
  | { type: "TOGGLE_COURSE_EXCLUSION"; courseId: number }
  | { type: "SET_MIN_CREDITS"; value: number | null }
  | { type: "SET_MAX_CREDITS"; value: number | null }
  | { type: "TOGGLE_SUMMER"; allow: boolean }
  | { type: "SET_SUMMER_MAX_CREDITS"; value: number }
  | { type: "TOGGLE_CREDIT_MINIMUM"; enforce: boolean }
  | { type: "TOGGLE_EXCLUDED_TERM"; termId: number }
  | { type: "SET_OBJECTIVE_ORDER"; order: OptimizationObjectiveType[] }
  | { type: "RESET" }

/** Apply one wizard action to the draft, returning a new draft (never mutating the input). */
function reducer(draft: WizardDraft, action: Action): WizardDraft {
  switch (action.type) {
    case "GO_TO_STEP":
      return { ...draft, step: clampStep(action.step) }
    case "SET_STUDENT_NAME":
      return { ...draft, studentDisplayName: action.name }
    case "SET_COLLEGE":
      // Changing school invalidates any program picked from the previous
      // school's list, and with it every downstream elective choice.
      return draft.collegeId === action.collegeId
        ? draft
        : {
            ...draft,
            collegeId: action.collegeId,
            primaryProgramId: null,
            additionalPrograms: [],
            courseChoices: {},
            excludedCourseIds: [],
          }
    case "SET_START_TERM":
      return { ...draft, startTermId: action.termId }
    case "SET_TARGET_TERM":
      return { ...draft, targetGraduationTermId: action.termId }
    case "SET_PRIMARY_PROGRAM":
      return draft.primaryProgramId === action.programId
        ? draft
        : { ...draft, primaryProgramId: action.programId, courseChoices: {}, excludedCourseIds: [] }
    case "ADD_ADDITIONAL_PROGRAM":
      return {
        ...draft,
        additionalPrograms: [...draft.additionalPrograms, action.program],
        courseChoices: {},
        excludedCourseIds: [],
      }
    case "REMOVE_ADDITIONAL_PROGRAM":
      return {
        ...draft,
        additionalPrograms: draft.additionalPrograms.filter((p) => p.academicProgramId !== action.programId),
        courseChoices: {},
        excludedCourseIds: [],
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
    case "TOGGLE_COURSE_CHOICE":
      return {
        ...draft,
        courseChoices: {
          ...draft.courseChoices,
          [action.choiceId]: toggleSelection(
            draft.courseChoices[action.choiceId] ?? [],
            action.courseId,
            action.maxSelections,
          ),
        },
        // Picking a course only makes sense if it isn't also excluded.
        excludedCourseIds: draft.excludedCourseIds.filter((id) => id !== action.courseId),
      }
    case "CLEAR_COURSE_CHOICE": {
      const { [action.choiceId]: _removed, ...rest } = draft.courseChoices
      return { ...draft, courseChoices: rest }
    }
    case "TOGGLE_COURSE_EXCLUSION": {
      const excludedCourseIds = toggleMembership(draft.excludedCourseIds, action.courseId)
      return {
        ...draft,
        excludedCourseIds,
        // Excluding a course only makes sense if it isn't also picked anywhere.
        courseChoices: excludedCourseIds.includes(action.courseId)
          ? removeCourseFromAllChoices(draft.courseChoices, action.courseId)
          : draft.courseChoices,
      }
    }
    case "SET_MIN_CREDITS":
      return { ...draft, defaultMinimumCredits: action.value }
    case "SET_MAX_CREDITS":
      return { ...draft, defaultMaximumCredits: action.value }
    case "TOGGLE_SUMMER":
      return { ...draft, allowSummer: action.allow }
    case "SET_SUMMER_MAX_CREDITS":
      return { ...draft, summerMaximumCredits: action.value }
    case "TOGGLE_CREDIT_MINIMUM":
      return { ...draft, enforceProgramCreditMinimum: action.enforce }
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

/** Keep a step number inside the wizard's real range. */
function clampStep(step: number): number {
  return Math.min(Math.max(step, 1), WIZARD_STEP_COUNT)
}

/** Add `id` to `ids` if absent, or remove it if present. */
function toggleMembership(ids: number[], id: number): number[] {
  return ids.includes(id) ? ids.filter((existing) => existing !== id) : [...ids, id]
}

/** Toggle one course inside a requirement choice, dropping the oldest selection
 * once the choice's allowance is used up (so clicking a new option always works
 * instead of silently doing nothing). */
function toggleSelection(selected: number[], courseId: number, maxSelections: number): number[] {
  if (selected.includes(courseId)) return selected.filter((id) => id !== courseId)
  const next = [...selected, courseId]
  return next.length > maxSelections ? next.slice(next.length - maxSelections) : next
}

/** Remove `courseId` from every choice's picks, wherever it happens to appear. */
function removeCourseFromAllChoices(choices: Record<string, number[]>, courseId: number): Record<string, number[]> {
  return Object.fromEntries(
    Object.entries(choices).map(([choiceId, picked]) => [choiceId, picked.filter((id) => id !== courseId)]),
  )
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

/** Read and update the in-progress scenario draft shared across every wizard step. */
export function useScenarioBuilder(): ScenarioBuilderContextValue {
  const context = useContext(ScenarioBuilderContext)
  if (context === null) {
    throw new Error("useScenarioBuilder must be used within a ScenarioBuilderProvider")
  }
  return context
}

/** Every academic_program_id in the draft (primary major first), the shape both
 * the requirement-choices query and the scenario payload need. */
export function selectedProgramIds(draft: WizardDraft): number[] {
  const ids = draft.primaryProgramId === null ? [] : [draft.primaryProgramId]
  return [...ids, ...draft.additionalPrograms.map((program) => program.academicProgramId)]
}

/** The catalog course_ids the student reported as already completed (transfer
 * credit with no catalog match has no course_id and is excluded). */
export function completedCourseIds(draft: WizardDraft): number[] {
  return draft.completedCourses
    .map((credit) => credit.course_id)
    .filter((courseId): courseId is number => courseId != null)
}
