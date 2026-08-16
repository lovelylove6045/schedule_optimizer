import { useEffect, useState } from "react"
import { Link, useLocation, useParams } from "react-router-dom"
import { CalendarSearch, PencilLine, RefreshCcw, X } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { EmptyState } from "@/components/shared/empty-state"
import { ErrorState } from "@/components/shared/error-state"
import { LoadingState } from "@/components/shared/loading-state"
import { PlanBoard } from "@/components/plans/plan-board"
import { PlanComparisonTable } from "@/components/plans/plan-comparison-table"
import { PlanOverlapSuggestions } from "@/components/plans/plan-overlap-suggestions"
import { RequirementCoverageTree } from "@/components/plans/requirement-coverage-tree"
import { SelectedProgramsBar } from "@/components/plans/selected-programs-bar"
import { useGenerateAlternativePlansMutation, useGeneratePlansMutation } from "@/hooks/use-scenario-mutations"
import { useScenarioPlansQuery } from "@/hooks/use-plan-queries"
import { OBJECTIVE_LABELS } from "@/lib/objective-labels"
import type { DegreePlanOut, OptimizationObjectiveType } from "@/lib/types"
import { CatalogSnapshotNotice } from "@/components/catalog/catalog-snapshot-notice"

interface LocationState {
  plans?: DegreePlanOut[]
}

/** Route entry point for "/plans/:scenarioId": tabbed results (plan board, comparison,
 * requirement coverage). */
export function PlansPage() {
  const params = useParams<{ scenarioId: string }>()
  const scenarioId = Number(params.scenarioId)
  const location = useLocation()
  const passedPlans = (location.state as LocationState | null)?.plans
  const scenarioPlansQuery = useScenarioPlansQuery(passedPlans ? undefined : scenarioId)
  const regenerate = useGeneratePlansMutation()
  const generateAlternatives = useGenerateAlternativePlansMutation()
  const [regeneratedPlans, setRegeneratedPlans] = useState<DegreePlanOut[] | null>(null)
  const [swappedPlansById, setSwappedPlansById] = useState<Record<number, DegreePlanOut>>({})
  const basePlans = regeneratedPlans ?? passedPlans ?? scenarioPlansQuery.data
  const plans = basePlans?.map((plan) => swappedPlansById[plan.degree_plan_id] ?? plan)
  const [selectedPlanId, setSelectedPlanId] = useState<number | null>(null)
  const [compareBoardPlanId, setCompareBoardPlanId] = useState<number | null>(null)
  const [alternativesAttempted, setAlternativesAttempted] = useState(false)
  useEffect(() => {
    if (!passedPlans || passedPlans.length !== 1 || alternativesAttempted || passedPlans[0].status === "INFEASIBLE") return
    setAlternativesAttempted(true)
    void generateAlternatives
      .mutateAsync(scenarioId)
      .then((alternatives) => {
        setRegeneratedPlans([...passedPlans, ...alternatives])
        if (alternatives.length === 0) {
          toast.info("No distinct alternatives were found within the solver time limit.")
        }
      })
      .catch(() => toast.info("The recommended plan is ready, but alternatives could not be generated."))
  }, [alternativesAttempted, generateAlternatives, passedPlans, scenarioId])
  /** Apply a plan-board swap's resulting plan to this page's displayed list,
   * whichever source (freshly generated, passed via navigation, or refetched)
   * that list currently came from. */
  function handlePlanUpdated(updatedPlan: DegreePlanOut) {
    setSwappedPlansById((prev) => ({ ...prev, [updatedPlan.degree_plan_id]: updatedPlan }))
  }
  /** Re-run the optimizer for this scenario and apply its fresh plans to this
   * page's displayed list, clearing any now-stale swap overrides/comparison
   * selection. Shared by the manual "Regenerate" button and the overlap
   * suggestions panel (accepting a suggestion also needs a regenerate) --
   * each does its own toast around this. */
  async function regenerateAndApply(): Promise<DegreePlanOut[]> {
    const fresh = await regenerate.mutateAsync(scenarioId)
    setRegeneratedPlans(fresh)
    setSwappedPlansById({})
    setCompareBoardPlanId(null)
    return fresh
  }
  /** Re-run the optimizer for this scenario, reporting the outcome as a toast. */
  async function handleRegenerate() {
    const pending = toast.loading("Re-running the optimizer…")
    try {
      const fresh = await regenerateAndApply()
      toast.success(`Generated ${fresh.length} plan${fresh.length === 1 ? "" : "s"}`, { id: pending })
    } catch (error) {
      toast.error("Couldn't generate plans", {
        id: pending,
        description: error instanceof Error ? error.message : undefined,
      })
    }
  }
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
          <Button onClick={handleRegenerate} disabled={regenerate.isPending}>
            <RefreshCcw className="size-4" />
            {regenerate.isPending ? "Generating…" : "Generate plans"}
          </Button>
        }
      />
    )
  }
  const recommendedPlan = plans[0]
  const coveragePlan = plans.find((plan) => plan.degree_plan_id === selectedPlanId) ?? recommendedPlan
  const compareBoardPlan = plans.find((plan) => plan.degree_plan_id === compareBoardPlanId) ?? null
  return (
    <PlansContent
      scenarioId={scenarioId}
      plans={plans}
      recommendedPlan={recommendedPlan}
      coveragePlan={coveragePlan}
      compareBoardPlan={compareBoardPlan}
      alternativesPending={generateAlternatives.isPending}
      regeneratePending={regenerate.isPending}
      onRegenerate={handleRegenerate}
      onRegenerateAndApply={regenerateAndApply}
      onPlanUpdated={handlePlanUpdated}
      onSelectCoveragePlan={setSelectedPlanId}
      onSelectComparePlan={setCompareBoardPlanId}
    />
  )
}

interface PlansContentProps {
  scenarioId: number
  plans: DegreePlanOut[]
  recommendedPlan: DegreePlanOut
  coveragePlan: DegreePlanOut
  compareBoardPlan: DegreePlanOut | null
  alternativesPending: boolean
  regeneratePending: boolean
  onRegenerate: () => void
  onRegenerateAndApply: () => Promise<DegreePlanOut[]>
  onPlanUpdated: (plan: DegreePlanOut) => void
  onSelectCoveragePlan: (planId: number) => void
  onSelectComparePlan: (planId: number | null) => void
}

/** Render the stable results chrome around the plan tabs. */
function PlansContent(props: PlansContentProps) {
  return (
    <div className="space-y-6">
      <ResultsHeader
        planCount={props.plans.length}
        alternativesPending={props.alternativesPending}
        regeneratePending={props.regeneratePending}
        onRegenerate={props.onRegenerate}
      />
      <CatalogSnapshotNotice />
      <p className="rounded-lg border bg-muted/30 p-3 text-xs text-muted-foreground">
        Prototype planning recommendation based on the FA26 catalog dataset. Confirm final graduation requirements,
        substitutions, approvals, and non-course obligations with an academic advisor.
      </p>
      <SelectedProgramsBar scenarioId={props.scenarioId} />
      <PlanOverlapSuggestions scenarioId={props.scenarioId} onRegenerate={props.onRegenerateAndApply} />
      <PlanResultTabs {...props} />
    </div>
  )
}

/** Show result count, background-generation status, and top-level actions. */
function ResultsHeader({ planCount, alternativesPending, regeneratePending, onRegenerate }: {
  planCount: number
  alternativesPending: boolean
  regeneratePending: boolean
  onRegenerate: () => void
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-extrabold tracking-tight sm:text-2xl">Your degree plans</h1>
        <p className="text-sm text-muted-foreground">
          {planCount} plan{planCount === 1 ? "" : "s"} available for this scenario.
        </p>
        {alternativesPending ? <p className="text-xs text-muted-foreground">Generating alternatives…</p> : null}
      </div>
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" size="sm" asChild><Link to="/"><PencilLine className="size-4" />Start over</Link></Button>
        <Button variant="outline" size="sm" onClick={onRegenerate} disabled={regeneratePending}>
          <RefreshCcw className="size-4" />{regeneratePending ? "Generating…" : "Regenerate"}
        </Button>
      </div>
    </div>
  )
}

/** Render recommended, comparison, and requirement-coverage tabs. */
function PlanResultTabs(props: PlansContentProps) {
  return (
    <Tabs defaultValue="recommended">
      <TabsList>
        <TabsTrigger value="recommended">Recommended plan</TabsTrigger>
        <TabsTrigger value="compare">Compare alternatives</TabsTrigger>
        <TabsTrigger value="coverage">Requirement coverage</TabsTrigger>
      </TabsList>
      <TabsContent value="recommended" className="pt-4">
        <PlanBoard plan={props.recommendedPlan} onPlanUpdated={props.onPlanUpdated} />
      </TabsContent>
      <TabsContent value="compare" className="space-y-4 pt-4">
        <PlanComparisonTable planIds={props.plans.map((plan) => plan.degree_plan_id)} onViewPlan={props.onSelectComparePlan} />
        {props.compareBoardPlan ? (
          <div className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-sm font-semibold text-muted-foreground">{planLabel(props.compareBoardPlan)} -- full schedule</h2>
              <Button variant="ghost" size="sm" onClick={() => props.onSelectComparePlan(null)}><X className="size-4" />Close</Button>
            </div>
            <PlanBoard plan={props.compareBoardPlan} onPlanUpdated={props.onPlanUpdated} />
          </div>
        ) : null}
      </TabsContent>
      <TabsContent value="coverage" className="space-y-4 pt-4">
        {props.plans.length > 1 ? (
          <Select value={String(props.coveragePlan.degree_plan_id)} onValueChange={(value) => props.onSelectCoveragePlan(Number(value))}>
            <SelectTrigger className="w-full sm:w-80"><SelectValue /></SelectTrigger>
            <SelectContent>
              {props.plans.map((plan) => <SelectItem key={plan.degree_plan_id} value={String(plan.degree_plan_id)}>{planLabel(plan)}</SelectItem>)}
            </SelectContent>
          </Select>
        ) : null}
        <RequirementCoverageTree degreePlanId={props.coveragePlan.degree_plan_id} />
      </TabsContent>
    </Tabs>
  )
}

/** Human label for a plan. `plan_name` is literally the OptimizationObjectiveType the
 * solver used (see `optimizer_persistence._create_degree_plan`), so it maps straight
 * through the shared objective-label table. */
function planLabel(plan: DegreePlanOut): string {
  const label = OBJECTIVE_LABELS[plan.plan_name as OptimizationObjectiveType]
  return label?.title ?? plan.plan_name ?? `Plan #${plan.degree_plan_id}`
}
