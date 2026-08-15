import { useState } from "react"
import { useLocation, useParams } from "react-router-dom"
import { CalendarSearch, RefreshCcw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { EmptyState } from "@/components/shared/empty-state"
import { ErrorState } from "@/components/shared/error-state"
import { LoadingState } from "@/components/shared/loading-state"
import { PlanBoard } from "@/components/plans/plan-board"
import { PlanComparisonTable } from "@/components/plans/plan-comparison-table"
import { RequirementCoverageTree } from "@/components/plans/requirement-coverage-tree"
import { useGeneratePlansMutation } from "@/hooks/use-scenario-mutations"
import { useScenarioPlansQuery } from "@/hooks/use-plan-queries"
import type { DegreePlanOut } from "@/lib/types"

interface LocationState {
  plans?: DegreePlanOut[]
}

/** Route entry point for "/plans/:scenarioId": tabbed results for Screens 6-8. */
export function PlansPage() {
  const params = useParams<{ scenarioId: string }>()
  const scenarioId = Number(params.scenarioId)
  const location = useLocation()
  const passedPlans = (location.state as LocationState | null)?.plans
  const scenarioPlansQuery = useScenarioPlansQuery(passedPlans ? undefined : scenarioId)
  const regenerate = useGeneratePlansMutation()
  const [regeneratedPlans, setRegeneratedPlans] = useState<DegreePlanOut[] | null>(null)
  const plans = regeneratedPlans ?? passedPlans ?? scenarioPlansQuery.data
  const [selectedPlanId, setSelectedPlanId] = useState<number | null>(null)
  if (!passedPlans && scenarioPlansQuery.isLoading) return <LoadingState label="Loading your plans…" />
  if (!passedPlans && scenarioPlansQuery.isError) {
    return <ErrorState message="Couldn't load this scenario's plans." onRetry={() => scenarioPlansQuery.refetch()} />
  }
  if (!plans || plans.length === 0) {
    return (
      <EmptyState
        icon={CalendarSearch}
        title="No plans generated yet"
        description="This scenario doesn't have any generated plans yet."
        action={
          <Button
            onClick={async () => setRegeneratedPlans(await regenerate.mutateAsync(scenarioId))}
            disabled={regenerate.isPending}
          >
            <RefreshCcw className="size-4" />
            {regenerate.isPending ? "Generating…" : "Generate plans"}
          </Button>
        }
      />
    )
  }
  const recommendedPlan = plans[0]
  const coveragePlan = plans.find((plan) => plan.degree_plan_id === selectedPlanId) ?? recommendedPlan
  return (
    <Tabs defaultValue="recommended">
      <TabsList>
        <TabsTrigger value="recommended">Recommended plan</TabsTrigger>
        <TabsTrigger value="compare">Compare alternatives</TabsTrigger>
        <TabsTrigger value="coverage">Requirement coverage</TabsTrigger>
      </TabsList>
      <TabsContent value="recommended" className="pt-4">
        <PlanBoard plan={recommendedPlan} />
      </TabsContent>
      <TabsContent value="compare" className="pt-4">
        <PlanComparisonTable planIds={plans.map((plan) => plan.degree_plan_id)} />
      </TabsContent>
      <TabsContent value="coverage" className="space-y-4 pt-4">
        {plans.length > 1 ? (
          <Select
            value={String(coveragePlan.degree_plan_id)}
            onValueChange={(value) => setSelectedPlanId(Number(value))}
          >
            <SelectTrigger className="w-full sm:w-72">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {plans.map((plan) => (
                <SelectItem key={plan.degree_plan_id} value={String(plan.degree_plan_id)}>
                  {plan.plan_name ?? `Plan #${plan.degree_plan_id}`}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : null}
        <RequirementCoverageTree degreePlanId={coveragePlan.degree_plan_id} />
      </TabsContent>
    </Tabs>
  )
}
