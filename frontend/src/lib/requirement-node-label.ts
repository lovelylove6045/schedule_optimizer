import type { RequirementNodeOut } from "@/lib/types"

/** Return the best available display label for a requirement node: its own
 * name, the course/course-group it points to, a CREDIT_REQUIREMENT's credit
 * total, or a plain-language description of its rule_operator. Shared by the
 * plan board's requirement-coverage tree and the catalog browser's raw
 * requirement tree so both describe the same node the same way. */
export function requirementNodeLabel(node: RequirementNodeOut): string {
  if (node.node_name) return node.node_name
  if (node.required_course) {
    return `${node.required_course.subject_code} ${node.required_course.course_number} — ${node.required_course.course_title}`
  }
  if (node.course_group) return node.course_group.course_group_name
  if (node.node_type === "CREDIT_REQUIREMENT" && node.required_credit_hours) {
    return `${node.required_credit_hours} credit hours (needs advisor sign-off)`
  }
  return requirementOperatorLabel(node)
}

/** Describe a container node's rule_operator in plain language, for nodes with no explicit name. */
export function requirementOperatorLabel(node: RequirementNodeOut): string {
  if (node.node_operator === "ANY") return "Any of the following"
  if (node.node_operator === "N_OF") return `${node.required_count ?? 1} of the following`
  if (node.node_operator === "CREDITS_FROM" || node.node_operator === "UNITS_FROM") {
    return `${node.required_credit_hours ?? 0} credit hours from the following`
  }
  return "All of the following"
}
