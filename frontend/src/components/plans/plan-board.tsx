import { CalendarX } from "lucide-react"
import { EmptyState } from "@/components/shared/empty-state"
import { ErrorState } from "@/components/shared/error-state"
import { LoadingState } from "@/components/shared/loading-state"
import { PlanCourseCard } from "@/components/plans/plan-course-card"
import { PlanSummaryCard } from "@/components/plans/plan-summary-card"
import { TermRibbon, type TermRibbonItem } from "@/components/layout/term-ribbon"
import { useTermsQuery } from "@/hooks/use-terms"
import type { DegreePlanOut, PlanCourseOut, TermOut } from "@/lib/types"

interface PlanBoardProps {
  plan: DegreePlanOut
}

/** Screen 6: a semester-by-semester board, the term columns headed by the
 * same Term Ribbon pill used as the wizard's progress stepper. */
export function PlanBoard({ plan }: PlanBoardProps) {
  const termsQuery = useTermsQuery()
  if (termsQuery.isPending) return <LoadingState label="Loading terms…" />
  if (termsQuery.isError) return <ErrorState message="Couldn't load terms from the server." />
  if (plan.status === "INFEASIBLE" || plan.courses.length === 0) {
    return (
      <div className="space-y-6">
        <PlanSummaryCard plan={plan} />
        <EmptyState
          icon={CalendarX}
          title="No schedule to show"
          description="This scenario couldn't be scheduled -- see the messages above for why, then adjust your constraints and try again."
        />
      </div>
    )
  }
  const termsById = new Map(termsQuery.data.map((term) => [term.term_id, term]))
  const columns = groupCoursesByTerm(plan.courses, termsById)
  const ribbonItems: TermRibbonItem[] = columns.map(({ term }) => ({
    id: term.term_id,
    label: term.term_code,
    state: "current",
  }))
  return (
    <div className="space-y-6">
      <PlanSummaryCard plan={plan} />
      <TermRibbon items={ribbonItems} className="hidden sm:flex" />
      <div className="grid snap-x grid-flow-col auto-cols-[minmax(220px,1fr)] gap-4 overflow-x-auto pb-2">
        {columns.map(({ term, courses, totalCredits }) => (
          <div key={term.term_id} className="flex snap-start flex-col gap-3 rounded-xl border bg-muted/30 p-3">
            <div className="flex items-baseline justify-between">
              <p className="font-semibold">{term.term_code}</p>
              <p className="font-mono text-xs text-muted-foreground">{totalCredits} cr</p>
            </div>
            {courses.map((planCourse) => (
              <PlanCourseCard key={planCourse.plan_course_id} planCourse={planCourse} />
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}

interface TermColumn {
  term: TermOut
  courses: PlanCourseOut[]
  totalCredits: number
}

/** Bucket a plan's courses into one column per term, ordered chronologically. */
function groupCoursesByTerm(courses: PlanCourseOut[], termsById: Map<number, TermOut>): TermColumn[] {
  const columns = new Map<number, TermColumn>()
  for (const planCourse of courses) {
    const term = termsById.get(planCourse.term_id)
    if (!term) continue
    const column = columns.get(term.term_id) ?? { term, courses: [], totalCredits: 0 }
    column.courses.push(planCourse)
    column.totalCredits += planCourse.credit_hours
    columns.set(term.term_id, column)
  }
  return Array.from(columns.values()).sort((a, b) => a.term.sequence_index - b.term.sequence_index)
}
