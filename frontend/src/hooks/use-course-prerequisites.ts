import { useQuery } from "@tanstack/react-query"
import { getCoursePrerequisites } from "@/lib/api/courses"
import type { CourseOut, PrerequisiteNodeOut } from "@/lib/types"

/** The requisite types worth flagging as "still needs doing" ahead of a course:
 * PREREQUISITE and PRE_OR_COREQUISITE both must be satisfied by the time the
 * course starts (at the latest). COREQUISITE (same-term, fine to add together)
 * and RECOMMENDED (optional) aren't blocking, so they're left out. */
const BLOCKING_REQUISITE_TYPES = new Set(["PREREQUISITE", "PRE_OR_COREQUISITE"])

/** Fetch one course's prerequisite tree. Catalog data is effectively static, so
 * this is cached indefinitely once fetched -- no need to ever refetch it. */
export function useCoursePrerequisitesQuery(courseId: number | undefined) {
  return useQuery({
    queryKey: ["courses", courseId, "prerequisites"],
    queryFn: () => getCoursePrerequisites(courseId as number),
    enabled: courseId != null,
    staleTime: Infinity,
  })
}

/** One independent requirement extracted from a prerequisite tree: satisfied by
 * completing ANY ONE course in `options` (a plain single-course prerequisite is
 * just a one-item clause). Multiple clauses are implicitly AND-ed together. */
export interface PrerequisiteClause {
  options: CourseOut[]
}

/** Reduce a prerequisite tree down to the clauses a student hasn't satisfied
 * yet (against `satisfiedCourseIds`), respecting each GROUP node's ALL/ANY/N_OF
 * operator -- an ANY/N_OF subtree collapses into a single "any one of these"
 * clause instead of wrongly treating every alternative as separately mandatory
 * (a plain flatten would turn "one of ~60 math electives" into "all 60 required"). */
export function unmetPrerequisiteClauses(
  nodes: PrerequisiteNodeOut[],
  satisfiedCourseIds: number[],
): PrerequisiteClause[] {
  const clauses = nodes.flatMap((node) => andClausesForNode(node))
  return clauses.filter((clause) => !clause.options.some((course) => satisfiedCourseIds.includes(course.course_id)))
}

/** Every clause an AND context (a root list, or a GROUP with operator ALL)
 * independently requires. COURSE_GROUP/STANDING/EXAM/CONSENT leaves resolve to
 * no clause at all -- there's no specific course to point a student at. */
function andClausesForNode(node: PrerequisiteNodeOut): PrerequisiteClause[] {
  if (node.node_type === "COURSE") {
    return BLOCKING_REQUISITE_TYPES.has(node.requisite_type) && node.required_course
      ? [{ options: [node.required_course] }]
      : []
  }
  if (node.node_type !== "GROUP") return []
  if (node.rule_operator === "ANY" || node.rule_operator === "N_OF") {
    const options = dedupeCourses(node.children.flatMap((child) => coursesSatisfyingChoice(child)))
    return options.length > 0 ? [{ options }] : []
  }
  return node.children.flatMap((child) => andClausesForNode(child))
}

/** Every course that would, on its own, satisfy one branch of an ANY/N_OF
 * choice -- collapsing that branch's own internal structure, since inside a
 * choice what matters is "which courses count", not how that count is built. */
function coursesSatisfyingChoice(node: PrerequisiteNodeOut): CourseOut[] {
  if (node.node_type === "COURSE") {
    return BLOCKING_REQUISITE_TYPES.has(node.requisite_type) && node.required_course ? [node.required_course] : []
  }
  return node.children.flatMap((child) => coursesSatisfyingChoice(child))
}

function dedupeCourses(courses: CourseOut[]): CourseOut[] {
  const byId = new Map(courses.map((course) => [course.course_id, course]))
  return [...byId.values()]
}
