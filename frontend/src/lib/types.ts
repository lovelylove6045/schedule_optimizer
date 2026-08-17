/**
 * TypeScript mirrors of the backend's Pydantic schemas (backend/app/schemas/).
 * Kept as one file since they're small, read-only shapes shared across every
 * screen -- splitting per-resource would just add import overhead here.
 */

export type ProgramType = "MAJOR" | "MINOR" | "EMPHASIS" | "CERTIFICATE" | "UNIVERSITY_CORE"

export type ScenarioProgramRole = "PRIMARY_MAJOR" | "SECOND_MAJOR" | "MINOR" | "EMPHASIS"

export type OptimizationObjectiveType =
  | "EARLIEST_GRADUATION"
  | "MIN_ADDITIONAL_CREDITS"
  | "MAX_REQUIREMENT_OVERLAP"
  | "BALANCED_WORKLOAD"
  | "MIN_SUMMER_ENROLLMENT"

export type RequirementNodeType =
  | "ROOT"
  | "GROUP"
  | "COURSE"
  | "COURSE_GROUP"
  | "CONSTRAINT"
  | "NON_COURSE"
  | "CREDIT_REQUIREMENT"

export type RuleOperator = "ALL" | "ANY" | "N_OF" | "CREDITS_FROM" | "UNITS_FROM"

export type RequisiteType = "PREREQUISITE" | "COREQUISITE" | "PRE_OR_COREQUISITE" | "RECOMMENDED"

export type CourseRuleNodeType = "GROUP" | "COURSE" | "COURSE_GROUP" | "STANDING" | "EXAM" | "CONSENT"

export interface CourseOut {
  course_id: number
  subject_id: number
  subject_code: string
  course_number: string
  course_title: string
  credit_hours: number
  course_level: number
  fall_offered: boolean
  spring_offered: boolean
  summer_offered: boolean
  course_type: string
}

export interface CourseGroupOut {
  course_group_id: number
  course_group_code: string
  course_group_name: string
  course_group_type: string
  description: string | null
}

export interface CollegeOut {
  college_id: number
  college_code: string
  college_name: string
  is_active: boolean
}

export interface ProgramOut {
  academic_program_id: number
  department_id: number
  program_code: string
  program_name: string
  program_type: ProgramType
  total_credit_hours: number | null
  is_active: boolean
  department_code: string | null
  department_name: string | null
  college_id: number | null
  college_code: string | null
  college_name: string | null
  compatible_parent_program_ids: number[]
}

/** One suggested program (backend: `program_overlap_service`): how much of
 * *its own* requirements are already covered by another program's courses. */
export interface ProgramOverlapOut {
  academic_program_id: number
  program_code: string
  program_name: string
  program_type: ProgramType
  total_credit_hours: number | null
  overlap_course_count: number
  overlap_credit_hours: number
  overlap_ratio: number | null
  overlap_courses: CourseOut[]
}

export interface TermOut {
  term_id: number
  term_code: string
  academic_year: number
  term_type: string
  sequence_index: number
  start_date: string | null
  end_date: string | null
}

export interface RequirementNodeOut {
  requirement_node_id: number
  node_type: RequirementNodeType
  node_operator: RuleOperator | null
  node_name: string | null
  required_course: CourseOut | null
  course_group: CourseGroupOut | null
  required_credit_hours: number | null
  required_count: number | null
  minimum_grade: string | null
  minimum_course_level: number | null
  minimum_distinct_subjects: number | null
  display_order: number | null
  is_active: boolean
  source_text: string | null
  children: RequirementNodeOut[]
  satisfying_courses: CourseOut[]
  is_satisfied: boolean | null
  is_shared: boolean
}

export interface RequirementSetOut {
  requirement_set_id: number
  requirement_set_code: string
  requirement_set_name: string
  requirement_set_type: string
  description: string | null
  nodes: RequirementNodeOut[]
}

export type RequirementChoiceKind = "COURSE_GROUP" | "ANY_OF" | "N_OF"

/** One point in a program's requirement tree where more than one course would
 * satisfy the same requirement (backend: `schemas/choice.py`). */
export interface RequirementChoiceOut {
  choice_id: string
  requirement_node_id: number
  kind: RequirementChoiceKind
  label: string
  choose_count: number
  required_credit_hours: number | null
  academic_program_id: number
  program_name: string
  requirement_set_id: number
  requirement_set_name: string
  course_group_id: number | null
  total_option_count: number
  options: CourseOut[]
  options_truncated: boolean
  already_satisfied: boolean
}

/** One node of a course's prerequisite/corequisite tree (backend: `schemas/prerequisite.py`). */
export interface PrerequisiteNodeOut {
  course_rule_node_id: number
  requisite_type: RequisiteType
  node_type: CourseRuleNodeType
  rule_operator: RuleOperator | null
  required_course: CourseOut | null
  required_subject_id: number | null
  required_academic_program_id: number | null
  required_count: number | null
  minimum_grade: string | null
  minimum_total_credits: number | null
  minimum_course_level: number | null
  minimum_standing: string | null
  text_value: string | null
  source_text: string | null
  children: PrerequisiteNodeOut[]
}

export interface CourseGroupMembersOut {
  course_group: CourseGroupOut
  courses: CourseOut[]
}

export type ScenarioPreferenceType =
  | "REQUIRE_COURSE"
  | "PREFER_COURSE"
  | "AVOID_COURSE"
  | "FIX_COURSE_TO_TERM"
  | "PREFER_TAG"
  | "AVOID_TAG"

export interface ScenarioPreferenceIn {
  preference_type: ScenarioPreferenceType
  course_id?: number | null
  term_id?: number | null
  weight?: number | null
}

export interface ScenarioProgramIn {
  academic_program_id: number
  program_role: ScenarioProgramRole
}

export interface StudentCreditIn {
  course_id?: number | null
  source_type?: string
  status?: string
  term_id?: number | null
  external_course_code?: string | null
  external_course_title?: string | null
  credits_earned?: number | null
  grade?: string | null
  is_in_residence?: boolean
}

export interface ScenarioTermIn {
  term_id: number
  minimum_credits?: number | null
  maximum_credits?: number | null
  is_excluded?: boolean
}

export interface ScenarioObjectiveIn {
  objective_type: OptimizationObjectiveType
  weight?: number
  display_order?: number | null
}

export interface ScenarioCreate {
  student_id?: number | null
  student_display_name?: string | null
  start_term_id: number
  target_graduation_term_id?: number | null
  default_minimum_credits?: number | null
  default_maximum_credits?: number | null
  full_time_minimum_credits?: number | null
  allow_summer?: boolean
  summer_maximum_credits?: number
  enforce_program_credit_minimum?: boolean
  programs: ScenarioProgramIn[]
  completed_courses?: StudentCreditIn[]
  term_overrides?: ScenarioTermIn[]
  preferences?: ScenarioPreferenceIn[]
  objectives?: ScenarioObjectiveIn[]
}

export interface ScenarioCreateOut {
  planning_scenario_id: number
}

export interface PlanCourseOut {
  plan_course_id: number
  course: CourseOut
  term_id: number
  credit_hours: number
  placement_source: string
  academic_role: string
  is_removable: boolean
  is_movable: boolean
  is_replaceable: boolean
  selection_reasons: string[]
  programs: PlanCourseProgramOut[]
}

export interface PlanCourseProgramOut {
  program_code: string
  program_name: string
  program_role: ScenarioProgramRole
}

export interface OptimizationMessageOut {
  optimization_message_id: number
  severity: string
  message_code: string | null
  message_text: string
  requirement_node_id: number | null
  course_id: number | null
}

export interface DegreePlanOut {
  degree_plan_id: number
  planning_scenario_id: number
  plan_name: string | null
  status: string
  total_credit_hours: number | null
  scheduled_credit_hours: number | null
  additional_credit_hours: number | null
  projected_graduation_term_id: number | null
  solver_objective_value: number | null
  solver_status: string | null
  courses: PlanCourseOut[]
  messages: OptimizationMessageOut[]
}

export interface PlanMetricsOut {
  degree_plan_id: number
  plan_name: string | null
  status: string
  total_credit_hours: number | null
  additional_credit_hours: number | null
  projected_graduation_term_id: number | null
  max_term_credit_hours: number | null
  avg_term_credit_hours: number | null
  summer_term_count: number
  overlap_credit_hours: number
  workload_credit_spread: number | null
  max_high_level_courses: number
  high_level_course_spread: number
  selected_programs: string[]
  warning_codes: string[]
}

export interface PlanComparisonOut {
  plans: PlanMetricsOut[]
}

/** Body for `POST /plans/{degree_plan_id}/courses/{plan_course_id}/swap`. */
export interface PlanCourseSwapIn {
  new_course_id: number
}

/** Body for `POST /plans/{degree_plan_id}/courses`: add a brand-new course to a term. */
export interface PlanCourseAddIn {
  course_id: number
  term_id: number
}

export interface PlanCourseMoveIn {
  term_id: number
}

/** One already-selected program on a scenario (`GET`/`POST /scenarios/{id}/programs`). */
export interface ScenarioProgramOut {
  scenario_program_id: number
  academic_program_id: number
  program_role: ScenarioProgramRole
  program_code: string
  program_name: string
}
