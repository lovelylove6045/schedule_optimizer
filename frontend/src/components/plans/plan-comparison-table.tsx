import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { ErrorState } from "@/components/shared/error-state"
import { LoadingState } from "@/components/shared/loading-state"
import { EmptyState } from "@/components/shared/empty-state"
import { GitCompare } from "lucide-react"
import { OBJECTIVE_LABELS } from "@/lib/objective-labels"
import { usePlanComparisonQuery } from "@/hooks/use-plan-queries"
import type { OptimizationObjectiveType, PlanMetricsOut } from "@/lib/types"
import { useTermsQuery } from "@/hooks/use-terms"

interface PlanComparisonTableProps {
  planIds: number[]
}

/** Screen 7: side-by-side metrics for every generated plan, with a plain-language
 * summary of what each plan optimized for pulled from its objective-coded plan_name. */
export function PlanComparisonTable({ planIds }: PlanComparisonTableProps) {
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
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {plans.map((plan) => (
          <WhyThisDiffersCard key={plan.degree_plan_id} plan={plan} />
        ))}
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Plan</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Graduation</TableHead>
            <TableHead>Total credits</TableHead>
            <TableHead>Extra credits</TableHead>
            <TableHead>Max term</TableHead>
            <TableHead>Avg term</TableHead>
            <TableHead>Summer terms</TableHead>
            <TableHead>Overlap credits</TableHead>
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
              <TableCell className="font-mono">{plan.total_credit_hours ?? "—"}</TableCell>
              <TableCell className="font-mono">{plan.additional_credit_hours ?? "—"}</TableCell>
              <TableCell className="font-mono">{plan.max_term_credit_hours ?? "—"}</TableCell>
              <TableCell className="font-mono">{plan.avg_term_credit_hours ?? "—"}</TableCell>
              <TableCell className="font-mono">{plan.summer_term_count}</TableCell>
              <TableCell className="font-mono">{plan.overlap_credit_hours}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

/** A short plain-language card explaining what one plan optimized for. */
function WhyThisDiffersCard({ plan }: { plan: PlanMetricsOut }) {
  const label = OBJECTIVE_LABELS[plan.plan_name as OptimizationObjectiveType]
  return (
    <div className="rounded-lg border p-4">
      <p className="text-sm font-semibold">{planTitle(plan.plan_name)}</p>
      <p className="mt-1 text-xs text-muted-foreground">
        {label?.description ?? "A baseline schedule generated for comparison."}
      </p>
    </div>
  )
}

/** Convert a plan's objective-coded plan_name into a human-readable title. */
function planTitle(planName: string | null): string {
  const label = OBJECTIVE_LABELS[planName as OptimizationObjectiveType]
  return label?.title ?? planName ?? "Untitled plan"
}
