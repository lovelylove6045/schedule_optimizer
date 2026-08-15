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

export interface ProgramOut {
  academic_program_id: number
  department_id: number
  program_code: string
  program_name: string
  program_type: ProgramType
  total_credit_hours: number | null
  is_active: boolean
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
  programs: ScenarioProgramIn[]
  completed_courses?: StudentCreditIn[]
  term_overrides?: ScenarioTermIn[]
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
}

export interface PlanComparisonOut {
  plans: PlanMetricsOut[]
}
