import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { ErrorState } from "@/components/shared/error-state"
import { LoadingState } from "@/components/shared/loading-state"
import { EmptyState } from "@/components/shared/empty-state"
import { CalendarDays, GitCompare } from "lucide-react"
import { OBJECTIVE_LABELS } from "@/lib/objective-labels"
import { usePlanComparisonQuery } from "@/hooks/use-plan-queries"
import type { OptimizationObjectiveType, PlanMetricsOut } from "@/lib/types"
import { useTermsQuery } from "@/hooks/use-terms"
import { cn } from "@/lib/utils"

interface PlanComparisonTableProps {
  planIds: number[]
  /** Called with a plan's id when the user asks to see its full term-by-term
   * schedule (Screen 6's board) instead of just its aggregate metrics. */
  onViewPlan?: (degreePlanId: number) => void
}

/** Screen 7: side-by-side metrics for every generated plan, with a plain-language
 * summary of what each plan optimized for pulled from its objective-coded plan_name. */
export function PlanComparisonTable({ planIds, onViewPlan }: PlanComparisonTableProps) {
  const comparisonQuery = usePlanComparisonQuery(planIds)
  const termsQuery = useTermsQuery()
  if (comparisonQuery.isPending || termsQuery.isPending) return <LoadingState label="Comparing plans…" />
  if (comparisonQuery.isError || termsQuery.isError) {
    return <ErrorState message="Couldn't load plan comparison data." onRetry={() => comparisonQuery.refetch()} />
  }
  const plans = comparisonQuery.data.plans
  if (plans.length <= 1) {
    return (
      <EmptyState
        icon={GitCompare}
        title="Nothing to compare yet"
        description="Generate a scenario with more than one objective to see alternative plans side by side."
      />
    )
  }
  const termsById = new Map(termsQuery.data.map((term) => [term.term_id, term]))
  const best = bestValues(plans)
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {plans.map((plan) => (
          <WhyThisDiffersCard key={plan.degree_plan_id} plan={plan} plans={plans} onViewPlan={onViewPlan} />
        ))}
      </div>
      <div className="glass-panel scrollbar-slim overflow-x-auto rounded-xl p-1">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Plan</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Graduation</TableHead>
            <TableHead>Degree-applicable future credits</TableHead>
            <TableHead>Additional-program credits</TableHead>
            <TableHead>Max term</TableHead>
            <TableHead>Avg term</TableHead>
            <TableHead>Summer terms</TableHead>
            <TableHead>Overlap credits</TableHead>
            <TableHead>Credit spread</TableHead>
            <TableHead>Max 4000/5000 courses</TableHead>
            <TableHead>Programs</TableHead>
            <TableHead>Warnings</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {plans.map((plan) => (
            <TableRow key={plan.degree_plan_id}>
              <TableCell className="font-medium">{planTitle(plan.plan_name)}</TableCell>
              <TableCell>
                <Badge variant={plan.status === "INFEASIBLE" ? "destructive" : "outline"}>{plan.status}</Badge>
              </TableCell>
              <TableCell className="font-mono">
                {termsById.get(plan.projected_graduation_term_id ?? -1)?.term_code ?? "—"}
              </TableCell>
              <MetricCell value={plan.total_credit_hours} isBest={plan.total_credit_hours === best.totalCredits} />
              <MetricCell
                value={plan.additional_credit_hours}
                isBest={plan.additional_credit_hours === best.additionalCredits}
              />
              <MetricCell
                value={plan.max_term_credit_hours}
                isBest={plan.max_term_credit_hours === best.maxTermCredits}
              />
              <MetricCell value={plan.avg_term_credit_hours} isBest={false} />
              <MetricCell value={plan.summer_term_count} isBest={plan.summer_term_count === best.summerTerms} />
              <MetricCell value={plan.overlap_credit_hours} isBest={plan.overlap_credit_hours === best.overlapCredits} />
              <MetricCell value={plan.workload_credit_spread} isBest={plan.workload_credit_spread === best.creditSpread} />
              <MetricCell value={plan.max_high_level_courses} isBest={plan.max_high_level_courses === best.highLevelMaximum} />
              <TableCell className="min-w-56 text-xs">{plan.selected_programs.join(" · ") || "—"}</TableCell>
              <TableCell>{plan.warning_codes.length || "None"}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      </div>
      <p className="text-xs text-muted-foreground">
        A gold value is the best figure for that measure across these plans. "Best" here means lowest, except overlap
        credits where more shared coursework is better.
      </p>
    </div>
  )
}

/** One numeric metric cell, highlighted when it's the best value in its column. */
function MetricCell({ value, isBest }: { value: number | null; isBest: boolean }) {
  return (
    <TableCell className={cn("font-mono", isBest && value !== null && "font-bold text-gold")}>
      {value ?? "—"}
    </TableCell>
  )
}

interface BestValues {
  totalCredits: number | null
  additionalCredits: number | null
  maxTermCredits: number | null
  summerTerms: number | null
  overlapCredits: number | null
  creditSpread: number | null
  highLevelMaximum: number | null
}

/** The winning value per comparable column: lowest for cost-like measures, highest
 * for requirement overlap (UC-46's "consistent measures" across plans). */
function bestValues(plans: PlanMetricsOut[]): BestValues {
  return {
    totalCredits: extreme(plans.map((p) => p.total_credit_hours), Math.min),
    additionalCredits: extreme(plans.map((p) => p.additional_credit_hours), Math.min),
    maxTermCredits: extreme(plans.map((p) => p.max_term_credit_hours), Math.min),
    summerTerms: extreme(plans.map((p) => p.summer_term_count), Math.min),
    overlapCredits: extreme(plans.map((p) => p.overlap_credit_hours), Math.max),
    creditSpread: extreme(plans.map((p) => p.workload_credit_spread), Math.min),
    highLevelMaximum: extreme(plans.map((p) => p.max_high_level_courses), Math.min),
  }
}

/** Apply `pick` across the non-null values of one column, or null if none exist. */
function extreme(values: (number | null)[], pick: (...nums: number[]) => number): number | null {
  const present = values.filter((value): value is number => value !== null)
  return present.length === 0 ? null : pick(...present)
}

/** A short plain-language card explaining what one plan optimized for, with an
 * optional shortcut to view that plan's full term-by-term schedule. */
function WhyThisDiffersCard({
  plan,
  plans,
  onViewPlan,
}: {
  plan: PlanMetricsOut
  plans: PlanMetricsOut[]
  onViewPlan?: (degreePlanId: number) => void
}) {
  const label = OBJECTIVE_LABELS[plan.plan_name as OptimizationObjectiveType]
  return (
    <div className="glass-inset flex flex-col gap-3 rounded-xl p-4">
      <div>
        <p className="text-sm font-semibold">{planTitle(plan.plan_name)}</p>
        <p className="mt-1 text-xs text-muted-foreground">
          {label?.description ?? "A baseline schedule generated for comparison."}
        </p>
        <p className="mt-2 text-xs text-muted-foreground">{tradeoffSummary(plan, plans)}</p>
        {plan.warning_codes.length > 0 ? (
          <p className="mt-2 text-xs text-warning">Assumptions: {plan.warning_codes.join(", ")}</p>
        ) : null}
      </div>
      {onViewPlan ? (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="w-fit"
          onClick={() => onViewPlan(plan.degree_plan_id)}
        >
          <CalendarDays className="size-4" />
          View schedule
        </Button>
      ) : null}
    </div>
  )
}

/** Explain metric-backed strengths and tradeoffs without inventing academic claims. */
function tradeoffSummary(plan: PlanMetricsOut, plans: PlanMetricsOut[]): string {
  const best = bestValues(plans)
  const details: string[] = []
  if (plan.additional_credit_hours === best.additionalCredits) details.push("uses the fewest additional credits")
  if (plan.summer_term_count === best.summerTerms) details.push("uses the least summer enrollment")
  if (plan.workload_credit_spread === best.creditSpread) details.push("has the most even credit distribution")
  if (plan.max_high_level_courses === best.highLevelMaximum) details.push("limits clustered 4000/5000-level courses")
  if (plan.overlap_credit_hours === best.overlapCredits && plan.overlap_credit_hours > 0) details.push(`applies ${plan.overlap_credit_hours} credits across distinct requirement sets`)
  return details.length > 0 ? `This plan ${details.join(" and ")}.` : "This plan represents a different valid strategy tradeoff."
}

/** Convert a plan's objective-coded plan_name into a human-readable title. */
function planTitle(planName: string | null): string {
  const label = OBJECTIVE_LABELS[planName as OptimizationObjectiveType]
  return label?.title ?? planName ?? "Untitled plan"
}
