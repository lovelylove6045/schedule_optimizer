import { CalendarX, Palette, TriangleAlert } from "lucide-react"
import { AddCourseButton } from "@/components/plans/add-course-button"
import { EmptyState } from "@/components/shared/empty-state"
import { ErrorState } from "@/components/shared/error-state"
import { LoadingState } from "@/components/shared/loading-state"
import { PlanCourseCard } from "@/components/plans/plan-course-card"
import { PlanSummaryCard } from "@/components/plans/plan-summary-card"
import { TermRibbon, type TermRibbonItem } from "@/components/layout/term-ribbon"
import { usePlanSwapOptionsQuery } from "@/hooks/use-plan-queries"
import { useTermsQuery } from "@/hooks/use-terms"
import type { CourseOut, DegreePlanOut, OptimizationMessageOut, PlanCourseOut, TermOut } from "@/lib/types"
import { cn } from "@/lib/utils"

interface PlanBoardProps {
  plan: DegreePlanOut
  onPlanUpdated: (updatedPlan: DegreePlanOut) => void
}

const COURSE_CATEGORY_LEGEND = [
  { label: "Primary requirement", dot: "bg-blue-500", style: "border-blue-200 bg-blue-50 text-blue-800 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-200" },
  { label: "Shared", dot: "bg-emerald-500", style: "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200" },
  { label: "Additional program", dot: "bg-violet-500", style: "border-violet-200 bg-violet-50 text-violet-800 dark:border-violet-800 dark:bg-violet-950/40 dark:text-violet-200" },
  { label: "Degree-credit elective", dot: "bg-amber-500", style: "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200" },
  { label: "Exploratory", dot: "bg-slate-500", style: "border-slate-300 bg-slate-100 text-slate-800 dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-200" },
]

/** Explain the course-card color system with visible, accessible category chips. */
function CourseCategoryLegend() {
  return (
    <section className="rounded-xl border border-primary/15 bg-gradient-to-r from-primary/7 via-background to-gold/10 p-3 shadow-sm" aria-label="Course category legend">
      <div className="mb-2.5 flex items-center gap-2">
        <span className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
          <Palette className="size-4" aria-hidden="true" />
        </span>
        <div>
          <h2 className="text-sm font-semibold">Course color guide</h2>
          <p className="text-xs text-muted-foreground">Match each color to the left edge of a course card.</p>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        {COURSE_CATEGORY_LEGEND.map((item) => (
          <span key={item.label} className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold shadow-xs ${item.style}`}>
            <span className={`size-2.5 rounded-full ring-2 ring-background ${item.dot}`} aria-hidden="true" />
            {item.label}
          </span>
        ))}
      </div>
    </section>
  )
}

/** Explain one term-load problem and point to the highlighted repair control. */
function TermLoadNotice({ warning }: { warning: OptimizationMessageOut }) {
  const isUnderloaded = warning.message_code === "TERM_CREDIT_BELOW_MINIMUM"
  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 p-2.5 text-amber-950 shadow-sm" role="alert">
      <div className="flex items-start gap-2">
        <TriangleAlert className="mt-0.5 size-4 shrink-0 text-amber-600" aria-hidden="true" />
        <div className="min-w-0">
          <p className="text-xs font-semibold">{isUnderloaded ? "Add credits to this term" : "Move credits out of this term"}</p>
          <p className="mt-1 text-[0.7rem] leading-relaxed text-amber-800">{warning.message_text}</p>
          <p className="mt-1.5 text-[0.68rem] font-medium text-amber-700">
            {isUnderloaded ? "Use the highlighted button below." : "Use a highlighted calendar button on a course below."}
          </p>
        </div>
      </div>
    </div>
  )
}

/** Screen 6: a semester-by-semester board, the term columns headed by the
 * same Term Ribbon pill used as the wizard's progress stepper. Each course
 * tile that satisfies a choice-shaped requirement (a course group, or a
 * literal "A or B" alternative) can be swapped in place for the same term. */
export function PlanBoard({ plan, onPlanUpdated }: PlanBoardProps) {
  const termsQuery = useTermsQuery()
  const swapOptionsQuery = usePlanSwapOptionsQuery(plan.degree_plan_id)
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
  const swapOptionsByPlanCourseId: Record<number, CourseOut[]> = swapOptionsQuery.data ?? {}
  const existingCourseIds = new Set(plan.courses.map((planCourse) => planCourse.course.course_id))
  const termLoadWarnings = plan.messages.filter((message) => message.message_code?.startsWith("TERM_CREDIT_"))
  return (
    <div className="space-y-6">
      <PlanSummaryCard plan={plan} />
      <CourseCategoryLegend />
      <TermRibbon items={ribbonItems} className="hidden sm:flex" />
      <div className="scrollbar-slim grid snap-x grid-flow-col auto-cols-[minmax(230px,1fr)] gap-4 overflow-x-auto pb-3">
        {columns.map(({ term, courses, totalCredits }) => {
          const warning = termLoadWarnings.find((message) => message.message_text.startsWith(term.term_code))
          const isOverloaded = warning?.message_code === "TERM_CREDIT_ABOVE_MAXIMUM"
          return (
            <div key={term.term_id} className={cn("glass-panel flex snap-start flex-col gap-3 rounded-xl p-3", warning && "border-amber-300 ring-2 ring-amber-200/70")}>
              <div className="flex items-baseline justify-between border-b pb-2">
                <p className="font-semibold">{term.term_code}</p>
                <p className={cn("font-mono text-xs text-muted-foreground", warning && "font-semibold text-amber-700")}>{totalCredits} cr</p>
              </div>
              {warning ? <TermLoadNotice warning={warning} /> : null}
              {courses.map((planCourse) => (
                <PlanCourseCard
                  key={planCourse.plan_course_id}
                  degreePlanId={plan.degree_plan_id}
                  planCourse={planCourse}
                  planCourses={plan.courses}
                  moveNeedsAttention={isOverloaded}
                  swapAlternatives={swapOptionsByPlanCourseId[planCourse.plan_course_id] ?? []}
                  onSwapped={onPlanUpdated}
                />
              ))}
              <AddCourseButton
                degreePlanId={plan.degree_plan_id}
                termId={term.term_id}
                termLabel={term.term_code}
                existingCourseIds={existingCourseIds}
                needsAttention={warning?.message_code === "TERM_CREDIT_BELOW_MINIMUM"}
                onAdded={onPlanUpdated}
              />
            </div>
          )
        })}
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
