import { useEffect, useState } from "react"
import { Link, useLocation, useParams } from "react-router-dom"
import { CalendarDays, CalendarSearch, GitCompareArrows, ListChecks, LoaderCircle, PencilLine, RefreshCcw, X } from "lucide-react"
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

interface AlternativeProgress {
  status: "running" | "complete"
  startedAt: number
  planCount: number
}

/** Return plans with the recommended strategy first while retaining alternative order. */
function orderPlansForDisplay(plans: DegreePlanOut[]): DegreePlanOut[] {
  const recommended = plans.filter((plan) => plan.plan_name === "RECOMMENDED")
  const alternatives = plans.filter((plan) => plan.plan_name !== "RECOMMENDED")
  return [...recommended, ...alternatives]
}

/** Format elapsed seconds as a compact minutes-and-seconds timer. */
function formatElapsedTime(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`
}

/** Track elapsed wall-clock seconds while alternative generation is active. */
function useElapsedSeconds(startedAt: number, active: boolean): number {
  const [elapsedSeconds, setElapsedSeconds] = useState(() => Math.floor((Date.now() - startedAt) / 1000))
  useEffect(() => {
    const updateElapsed = () => setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000))
    updateElapsed()
    if (!active) return undefined
    const intervalId = window.setInterval(updateElapsed, 1000)
    return () => window.clearInterval(intervalId)
  }, [active, startedAt])
  return elapsedSeconds
}

/** Route entry point for "/plans/:scenarioId": tabbed results (plan board, comparison,
 * requirement coverage). */
export function PlansPage() {
  const params = useParams<{ scenarioId: string }>()
  const scenarioId = Number(params.scenarioId)
  const location = useLocation()
  const passedPlans = (location.state as LocationState | null)?.plans
  const scenarioPlansQuery = useScenarioPlansQuery(scenarioId)
  const regenerate = useGeneratePlansMutation()
  const generateAlternatives = useGenerateAlternativePlansMutation()
  const [regeneratedPlans, setRegeneratedPlans] = useState<DegreePlanOut[] | null>(null)
  const [swappedPlansById, setSwappedPlansById] = useState<Record<number, DegreePlanOut>>({})
  const basePlans = regeneratedPlans ?? scenarioPlansQuery.data ?? passedPlans
  const plans = basePlans
    ? orderPlansForDisplay(basePlans).map((plan) => swappedPlansById[plan.degree_plan_id] ?? plan)
    : undefined
  const [selectedPlanId, setSelectedPlanId] = useState<number | null>(null)
  const [compareBoardPlanId, setCompareBoardPlanId] = useState<number | null>(null)
  const [alternativesAttempted, setAlternativesAttempted] = useState(false)
  const [alternativeProgress, setAlternativeProgress] = useState<AlternativeProgress | null>(null)
  useEffect(() => {
    const persistedPlans = scenarioPlansQuery.data
    if (!persistedPlans || persistedPlans.length !== 1 || alternativesAttempted || persistedPlans[0].status === "INFEASIBLE") return
    setAlternativesAttempted(true)
    setAlternativeProgress({ status: "running", startedAt: Date.now(), planCount: persistedPlans.length })
    void generateAlternatives
      .mutateAsync(scenarioId)
      .then((alternatives) => {
        const generatedPlans = orderPlansForDisplay([...persistedPlans, ...alternatives])
        setRegeneratedPlans(generatedPlans)
        setAlternativeProgress((progress) => progress ? { ...progress, status: "complete", planCount: generatedPlans.length } : null)
        if (alternatives.length === 0) {
          toast.info("No distinct alternatives were found within the solver time limit.")
        }
      })
      .catch(() => {
        setAlternativeProgress(null)
        toast.info("The recommended plan is ready, but alternatives could not be generated.")
      })
  }, [alternativesAttempted, generateAlternatives, scenarioId, scenarioPlansQuery.data])
  useEffect(() => {
    if (alternativeProgress?.status !== "complete") return undefined
    const timeoutId = window.setTimeout(() => setAlternativeProgress(null), 6000)
    return () => window.clearTimeout(timeoutId)
  }, [alternativeProgress?.status])
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
    try {
      const fresh = await regenerateAndApply()
      toast.success(`Generated ${fresh.length} plan${fresh.length === 1 ? "" : "s"}`)
    } catch (error) {
      toast.error("Couldn't generate plans", {
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
      alternativeProgress={alternativeProgress}
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
  alternativeProgress: AlternativeProgress | null
  regeneratePending: boolean
  onRegenerate: () => void
  onRegenerateAndApply: () => Promise<DegreePlanOut[]>
  onPlanUpdated: (plan: DegreePlanOut) => void
  onSelectCoveragePlan: (planId: number) => void
  onSelectComparePlan: (planId: number | null) => void
}

/** Render the stable results chrome around the plan tabs. */
function PlansContent(props: PlansContentProps) {
  const [activeTab, setActiveTab] = useState("recommended")
  /** Open the comparison tab and bring its content into view. */
  function showAlternatives() {
    setActiveTab("compare")
    window.setTimeout(() => document.getElementById("plan-result-tabs")?.scrollIntoView({ behavior: "smooth", block: "start" }), 0)
  }
  return (
    <div className="space-y-6">
      <ResultsHeader
        planCount={props.plans.length}
        regeneratePending={props.regeneratePending}
        onRegenerate={props.onRegenerate}
      />
      {props.alternativeProgress ? <AlternativeGenerationBanner progress={props.alternativeProgress} onCompare={showAlternatives} /> : null}
      <CatalogSnapshotNotice />
      <p className="rounded-lg border bg-muted/30 p-3 text-xs text-muted-foreground">
        Prototype planning recommendation based on the FA26 catalog dataset. Confirm final graduation requirements,
        substitutions, approvals, and non-course obligations with an academic advisor.
      </p>
      <SelectedProgramsBar scenarioId={props.scenarioId} />
      <PlanOverlapSuggestions scenarioId={props.scenarioId} onRegenerate={props.onRegenerateAndApply} />
      <PlanResultTabs {...props} activeTab={activeTab} onTabChange={setActiveTab} />
    </div>
  )
}

/** Show result count, background-generation status, and top-level actions. */
function ResultsHeader({ planCount, regeneratePending, onRegenerate }: {
  planCount: number
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

/** Show alternative generation count, elapsed time, and completion feedback. */
function AlternativeGenerationBanner({ progress, onCompare }: { progress: AlternativeProgress; onCompare: () => void }) {
  const isRunning = progress.status === "running"
  const elapsedSeconds = useElapsedSeconds(progress.startedAt, isRunning)
  const planLabel = `${progress.planCount} plan${progress.planCount === 1 ? "" : "s"} generated`
  return (
    <div className="glass-raised relative overflow-hidden rounded-2xl border-primary/25 p-4 shadow-md" role="status" aria-live="polite">
      <div className="optimization-pattern absolute inset-0 opacity-35" aria-hidden="true" />
      <div className="relative flex items-start gap-4">
        <span className="relative flex size-12 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm shadow-primary/20">
          <GitCompareArrows className="size-5" aria-hidden="true" />
          {isRunning ? <LoaderCircle className="absolute -top-1.5 -right-1.5 size-5 rounded-full bg-background p-0.5 text-gold motion-safe:animate-spin" aria-hidden="true" /> : null}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="text-sm font-semibold">{isRunning ? "Generating comparison plans" : "Comparison plans ready"}</h2>
              <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
                {isRunning
                  ? "Your recommended plan is ready. The optimizer is searching for the next distinct strategy."
                  : "The optimizer finished exploring distinct strategies. Your comparisons are ready to review."}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full border border-primary/20 bg-background/70 px-2.5 py-1 font-mono text-[0.7rem] font-semibold text-primary">
                {formatElapsedTime(elapsedSeconds)} {isRunning ? "elapsed" : "total"}
              </span>
              <span className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/8 px-2.5 py-1 text-[0.7rem] font-semibold text-primary">
                <span className={`size-1.5 rounded-full bg-success ${isRunning ? "motion-safe:animate-pulse" : ""}`} aria-hidden="true" />
                {planLabel}
              </span>
            </div>
          </div>
          {isRunning ? (
            <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-primary/10" aria-hidden="true">
              <div className="optimization-progress-sweep h-full w-2/5 rounded-full bg-gradient-to-r from-primary via-ring to-gold" />
            </div>
          ) : (
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <div className="h-1.5 min-w-36 flex-1 overflow-hidden rounded-full bg-primary/10" aria-hidden="true">
                <div className="h-full w-full rounded-full bg-success" />
              </div>
              {progress.planCount > 1 ? (
                <Button type="button" size="sm" onClick={onCompare}>
                  <GitCompareArrows className="size-4" />Compare alternatives
                </Button>
              ) : null}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

interface PlanResultTabsProps extends PlansContentProps {
  activeTab: string
  onTabChange: (value: string) => void
}

/** Render recommended, comparison, and requirement-coverage tabs. */
function PlanResultTabs(props: PlanResultTabsProps) {
  return (
    <Tabs id="plan-result-tabs" value={props.activeTab} onValueChange={props.onTabChange} className="scroll-mt-36 gap-0">
      <div className="glass-raised sticky top-[4.5rem] z-30 flex flex-col gap-2 rounded-xl border-primary/20 p-2 shadow-md backdrop-blur-xl sm:flex-row sm:items-center">
        <div className="flex shrink-0 items-center gap-2 px-2 sm:border-r sm:pr-4">
          <ListChecks className="size-4 text-primary" aria-hidden="true" />
          <span className="text-xs font-bold uppercase tracking-[0.12em] text-primary">Results view</span>
        </div>
        <TabsList className="grid h-auto! w-full flex-1 grid-cols-3 gap-1 rounded-lg bg-primary/7 p-1">
          <TabsTrigger value="recommended" className="group h-10 min-w-0 rounded-md px-2 data-[state=active]:border-primary data-[state=active]:bg-primary data-[state=active]:text-primary-foreground data-[state=active]:shadow-sm">
            <CalendarDays className="size-4 shrink-0 text-primary group-data-[state=active]:text-primary-foreground" aria-hidden="true" />
            <span className="truncate text-xs font-semibold sm:text-sm">Schedule</span>
          </TabsTrigger>
          <TabsTrigger value="compare" className="group h-10 min-w-0 rounded-md px-2 data-[state=active]:border-primary data-[state=active]:bg-primary data-[state=active]:text-primary-foreground data-[state=active]:shadow-sm">
            <GitCompareArrows className="size-4 shrink-0 text-primary group-data-[state=active]:text-primary-foreground" aria-hidden="true" />
            <span className="truncate text-xs font-semibold sm:text-sm">Compare</span>
          </TabsTrigger>
          <TabsTrigger value="coverage" className="group h-10 min-w-0 rounded-md px-2 data-[state=active]:border-primary data-[state=active]:bg-primary data-[state=active]:text-primary-foreground data-[state=active]:shadow-sm">
            <ListChecks className="size-4 shrink-0 text-primary group-data-[state=active]:text-primary-foreground" aria-hidden="true" />
            <span className="truncate text-xs font-semibold sm:text-sm">Requirements</span>
          </TabsTrigger>
        </TabsList>
      </div>
      <TabsContent value="recommended" className="pt-6">
        <PlanBoard plan={props.recommendedPlan} onPlanUpdated={props.onPlanUpdated} />
      </TabsContent>
      <TabsContent value="compare" className="space-y-4 pt-6">
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
      <TabsContent value="coverage" className="space-y-4 pt-6">
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
