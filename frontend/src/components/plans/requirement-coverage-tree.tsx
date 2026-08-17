import { BookCheck, Check, Circle, Sparkles } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { EmptyState } from "@/components/shared/empty-state"
import { ErrorState } from "@/components/shared/error-state"
import { LoadingState } from "@/components/shared/loading-state"
import { usePlanRequirementsQuery } from "@/hooks/use-plan-queries"
import { requirementNodeLabel } from "@/lib/requirement-node-label"
import type { CourseOut, RequirementNodeOut, RequirementSetOut } from "@/lib/types"
import { cn } from "@/lib/utils"

interface RequirementCoverageTreeProps {
  degreePlanId: number
}

/** Screen 8: every requirement node behind this plan's programs, showing which
 * are satisfied, remaining, or shared across more than one program. */
export function RequirementCoverageTree({ degreePlanId }: RequirementCoverageTreeProps) {
  const query = usePlanRequirementsQuery(degreePlanId)
  if (query.isPending) return <LoadingState label="Checking requirement coverage…" />
  if (query.isError) return <ErrorState message="Couldn't load requirement coverage." onRetry={() => query.refetch()} />
  if (query.data.length === 0) {
    return (
      <EmptyState
        icon={Sparkles}
        title="No requirement sets found"
        description="This scenario's programs don't have any linked requirement sets to check coverage against."
      />
    )
  }
  return (
    <div className="space-y-4">
      {query.data.map((requirementSet) => (
        <RequirementSetSection key={requirementSet.requirement_set_id} requirementSet={requirementSet} />
      ))}
    </div>
  )
}

/** One requirement_set's header plus its top-level node rows. */
function RequirementSetSection({ requirementSet }: { requirementSet: RequirementSetOut }) {
  return (
    <div className="glass-panel overflow-hidden rounded-xl">
      <div className="border-b px-4 py-2.5">
        <p className="text-sm font-semibold">{requirementSet.requirement_set_name}</p>
      </div>
      <ul className="divide-y">
        {requirementSet.nodes.map((node) => (
          <RequirementNodeRow key={node.requirement_node_id} node={node} depth={0} />
        ))}
      </ul>
    </div>
  )
}

/** One requirement node's row (status, label, shared badge) plus its indented children. */
function RequirementNodeRow({ node, depth }: { node: RequirementNodeOut; depth: number }) {
  const satisfyingCourses = node.satisfying_courses ?? []
  const displayedSatisfaction = directCourseDisplayStatus(node, satisfyingCourses)
  const shouldShowCourseEvidence = node.required_course === null && satisfyingCourses.length > 0
  return (
    <li>
      <div className="flex items-start gap-2 px-4 py-2.5" style={{ paddingLeft: `${1 + depth * 1.25}rem` }}>
        <StatusIcon isSatisfied={displayedSatisfaction} />
        <div className="min-w-0 flex-1">
          <p className="text-sm">{requirementNodeLabel(node)}</p>
          {node.source_text ? <p className="text-xs text-muted-foreground">{node.source_text}</p> : null}
          {shouldShowCourseEvidence ? (
            <SatisfyingCourseList courses={satisfyingCourses} isSatisfied={displayedSatisfaction === true} />
          ) : null}
        </div>
        {node.is_shared ? (
          <Badge className="shrink-0 bg-gold text-gold-foreground">Shared</Badge>
        ) : null}
      </div>
      {node.children.length > 0 ? (
        <ul className="divide-y">
          {node.children.map((child) => (
            <RequirementNodeRow key={child.requirement_node_id} node={child} depth={depth + 1} />
          ))}
        </ul>
      ) : null}
    </li>
  )
}

/** Show a direct course leaf as satisfied only when that leaf has an actual
 * planned/completed allocation, avoiding duplicate checks for equivalent alternatives. */
function directCourseDisplayStatus(node: RequirementNodeOut, satisfyingCourses: CourseOut[]): boolean | null {
  if (node.required_course !== null) return satisfyingCourses.length > 0
  return node.is_satisfied
}

/** Show the concrete courses allocated to an aggregate course-group requirement. */
function SatisfyingCourseList({ courses, isSatisfied }: { courses: CourseOut[]; isSatisfied: boolean }) {
  const appliedCredits = courses.reduce((total, course) => total + course.credit_hours, 0)
  return (
    <div className={cn("mt-2 rounded-lg border px-3 py-2", isSatisfied ? "border-success/20 bg-success/5" : "bg-muted/35")}>
      <p className={cn("mb-1.5 flex items-center gap-1.5 text-[0.7rem] font-semibold tracking-wide uppercase", isSatisfied ? "text-success" : "text-muted-foreground")}>
        <BookCheck className="size-3.5" aria-hidden="true" />
        {isSatisfied ? "Satisfied by" : "Courses applied"} · {courses.length} course{courses.length === 1 ? "" : "s"} · {appliedCredits.toLocaleString(undefined, { maximumFractionDigits: 2 })} credits
      </p>
      <ul className="flex flex-wrap gap-1.5">
        {courses.map((course) => <SatisfyingCourseChip key={course.course_id} course={course} />)}
      </ul>
    </div>
  )
}

/** Render one allocated course with enough detail to explain the match. */
function SatisfyingCourseChip({ course }: { course: CourseOut }) {
  return (
    <li className="rounded-md border border-success/20 bg-background/70 px-2 py-1 text-xs">
      <span className="font-semibold">{course.subject_code} {course.course_number}</span>
      <span className="text-muted-foreground"> · {course.course_title} · {course.credit_hours} cr</span>
    </li>
  )
}

/** A small circular marker: filled check when satisfied, hollow otherwise. */
function StatusIcon({ isSatisfied }: { isSatisfied: boolean | null }) {
  if (isSatisfied === true) {
    return (
      <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-success text-success-foreground">
        <Check className="size-3" aria-hidden="true" />
      </span>
    )
  }
  return (
    <span
      className={cn(
        "mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border",
        isSatisfied === false ? "border-muted-foreground/40" : "border-dashed border-muted-foreground/30",
      )}
    >
      <Circle className="size-2 fill-current text-muted-foreground/40" aria-hidden="true" />
    </span>
  )
}
