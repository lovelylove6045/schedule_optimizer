import { useEffect, useState } from "react"
import { Link, useLocation, useParams } from "react-router-dom"
import { CalendarDays, CalendarSearch, GitCompareArrows, ListChecks, LoaderCircle, PencilLine, RefreshCcw, TriangleAlert, X } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
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
import { useGenerateAlternativePlansMutation, useGenerateRecommendedPlanMutation } from "@/hooks/use-scenario-mutations"
import { useScenarioPlansQuery } from "@/hooks/use-plan-queries"
import { useScenarioProgramsQuery } from "@/hooks/use-scenario-queries"
import { OBJECTIVE_LABELS } from "@/lib/objective-labels"
import type { DegreePlanOut, OptimizationObjectiveType } from "@/lib/types"
import { CatalogSnapshotNotice } from "@/components/catalog/catalog-snapshot-notice"
import { OptimizationProgress, OptimizationWorkflow } from "@/components/wizard/optimization-progress"

interface LocationState {
  plans?: DegreePlanOut[]
}

interface AlternativeProgress {
  status: "running" | "complete"
  startedAt: number
  planCount: number
}

const ALTERNATIVE_STRATEGIES: OptimizationObjectiveType[] = [
  "EARLIEST_GRADUATION",
  "MIN_ADDITIONAL_CREDITS",
  "BALANCED_WORKLOAD",
  "MAX_REQUIREMENT_OVERLAP",
  "MIN_SUMMER_ENROLLMENT",
]

/** Return plans with the recommended strategy first while retaining alternative order. */
function orderPlansForDisplay(plans: DegreePlanOut[]): DegreePlanOut[] {
  const newestByStrategy = new Map<string, DegreePlanOut>()
  for (const plan of plans) {
    const strategy = plan.plan_name ?? `plan-${plan.degree_plan_id}`
    const current = newestByStrategy.get(strategy)
    if (!current || plan.degree_plan_id > current.degree_plan_id) newestByStrategy.set(strategy, plan)
  }
  const distinctPlans = [...newestByStrategy.values()]
  const recommended = distinctPlans.filter((plan) => plan.plan_name === "RECOMMENDED")
  const alternatives = distinctPlans.filter((plan) => plan.plan_name !== "RECOMMENDED")
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

/** Run user-requested alternative strategies and retain their progress and results. */
function useManualAlternativeGeneration(scenarioId: number, existingPlans: DegreePlanOut[]) {
  const mutation = useGenerateAlternativePlansMutation()
  const [progress, setProgress] = useState<AlternativeProgress | null>(null)
  const [generatedPlans, setGeneratedPlans] = useState<DegreePlanOut[]>([])
  useEffect(() => {
    if (progress?.status !== "complete") return undefined
    const timeoutId = window.setTimeout(() => setProgress(null), 6000)
    return () => window.clearTimeout(timeoutId)
  }, [progress?.status])
  /** Generate the selected strategies and publish completion feedback. */
  async function generate(objectiveTypes: OptimizationObjectiveType[]): Promise<void> {
    const startedAt = Date.now()
    const startingPlans = mergePlans(existingPlans, generatedPlans) ?? []
    setProgress({ status: "running", startedAt, planCount: startingPlans.length })
    try {
      const alternatives = await mutation.mutateAsync({ scenarioId, objectiveTypes })
      const mergedGeneratedPlans = mergePlans(generatedPlans, alternatives) ?? []
      const completedPlans = mergePlans(existingPlans, mergedGeneratedPlans) ?? []
      setGeneratedPlans(mergedGeneratedPlans)
      setProgress({ status: "complete", startedAt, planCount: completedPlans.length })
      if (alternatives.length === 0) toast.info("No new distinct plan was found for the selected strategies.")
    } catch (error) {
      setProgress(null)
      toast.error("Couldn't generate alternatives", { description: error instanceof Error ? error.message : undefined })
    }
  }
  return { generate, generatedPlans, progress, isPending: mutation.isPending }
}

/** Route entry point for "/plans/:scenarioId": tabbed results (plan board, comparison,
 * requirement coverage). */
export function PlansPage() {
  const params = useParams<{ scenarioId: string }>()
  const scenarioId = Number(params.scenarioId)
  const location = useLocation()
  const passedPlans = (location.state as LocationState | null)?.plans
  const scenarioPlansQuery = useScenarioPlansQuery(scenarioId)
  const scenarioProgramsQuery = useScenarioProgramsQuery(scenarioId)
  const regenerate = useGenerateRecommendedPlanMutation()
  const [regeneratedPlans, setRegeneratedPlans] = useState<DegreePlanOut[] | null>(null)
  const [swappedPlansById, setSwappedPlansById] = useState<Record<number, DegreePlanOut>>({})
  const persistedPlans = regeneratedPlans ?? scenarioPlansQuery.data ?? passedPlans
  const alternatives = useManualAlternativeGeneration(scenarioId, persistedPlans ?? [])
  const basePlans = mergePlans(persistedPlans, alternatives.generatedPlans)
  const plans = basePlans
    ? orderPlansForDisplay(basePlans).map((plan) => swappedPlansById[plan.degree_plan_id] ?? plan)
    : undefined
  const [selectedPlanId, setSelectedPlanId] = useState<number | null>(null)
  const [compareBoardPlanId, setCompareBoardPlanId] = useState<number | null>(null)
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
    const recommended = await regenerate.mutateAsync({ scenarioId })
    const fresh = [recommended]
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
      <>
        {regenerate.isPending ? <OptimizationProgress phase="solving" programCount={scenarioProgramsQuery.data?.length} /> : null}
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
      </>
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
      alternativeProgress={alternatives.progress}
      alternativeGenerationPending={alternatives.isPending}
      optimizationProgramCount={scenarioProgramsQuery.data?.length ?? 1}
      regeneratePending={regenerate.isPending}
      onRegenerate={handleRegenerate}
      onRegenerateAndApply={regenerateAndApply}
      onGenerateAlternatives={alternatives.generate}
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
  alternativeGenerationPending: boolean
  optimizationProgramCount: number
  regeneratePending: boolean
  onRegenerate: () => void
  onRegenerateAndApply: () => Promise<DegreePlanOut[]>
  onGenerateAlternatives: (objectiveTypes: OptimizationObjectiveType[]) => Promise<void>
  onPlanUpdated: (plan: DegreePlanOut) => void
  onSelectCoveragePlan: (planId: number) => void
  onSelectComparePlan: (planId: number | null) => void
}

/** Render the stable results chrome around the plan tabs. */
function PlansContent(props: PlansContentProps) {
  const [activeTab, setActiveTab] = useState("recommended")
  const [alternativeDialogOpen, setAlternativeDialogOpen] = useState(false)
  /** Open the comparison tab and bring its content into view. */
  function showAlternatives() {
    setActiveTab("compare")
    window.setTimeout(() => document.getElementById("plan-result-tabs")?.scrollIntoView({ behavior: "smooth", block: "start" }), 0)
  }
  return (
    <div className="space-y-6">
      {props.regeneratePending ? <OptimizationProgress phase="solving" programCount={props.optimizationProgramCount} /> : null}
      <ResultsHeader
        planCount={props.plans.length}
        regeneratePending={props.regeneratePending}
        actionsDisabled={props.regeneratePending || props.alternativeGenerationPending}
        onRegenerate={props.onRegenerate}
        onGenerateAlternatives={() => setAlternativeDialogOpen(true)}
        alternativesPending={props.alternativeGenerationPending}
      />
      {props.alternativeProgress ? <AlternativeGenerationBanner progress={props.alternativeProgress} programCount={props.optimizationProgramCount} onCompare={showAlternatives} /> : null}
      <CatalogSnapshotNotice />
      <p className="rounded-lg border bg-muted/30 p-3 text-xs text-muted-foreground">
        Prototype planning recommendation based on the FA26 catalog dataset. Confirm final graduation requirements,
        substitutions, approvals, and non-course obligations with an academic advisor.
      </p>
      <SelectedProgramsBar scenarioId={props.scenarioId} />
      <PlanOverlapSuggestions scenarioId={props.scenarioId} onRegenerate={props.onRegenerateAndApply} />
      <PlanResultTabs {...props} activeTab={activeTab} onTabChange={setActiveTab} onOpenAlternativeDialog={() => setAlternativeDialogOpen(true)} />
      <AlternativePlanDialog open={alternativeDialogOpen} pending={props.alternativeGenerationPending} programCount={props.optimizationProgramCount} onOpenChange={setAlternativeDialogOpen} onGenerate={props.onGenerateAlternatives} />
    </div>
  )
}

/** Show result count, background-generation status, and top-level actions. */
function ResultsHeader({ planCount, regeneratePending, alternativesPending, actionsDisabled, onRegenerate, onGenerateAlternatives }: {
  planCount: number
  regeneratePending: boolean
  alternativesPending: boolean
  actionsDisabled: boolean
  onRegenerate: () => void
  onGenerateAlternatives: () => void
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
        <Button variant="outline" size="sm" onClick={onGenerateAlternatives} disabled={actionsDisabled}>
          <GitCompareArrows className="size-4" />{alternativesPending ? "Generating alternatives…" : "Generate alternatives"}
        </Button>
        <Button variant="outline" size="sm" onClick={onRegenerate} disabled={actionsDisabled}>
          <RefreshCcw className="size-4" />{regeneratePending ? "Generating…" : "Regenerate"}
        </Button>
      </div>
    </div>
  )
}

/** Show alternative generation count, elapsed time, and completion feedback. */
function AlternativeGenerationBanner({ progress, programCount, onCompare }: { progress: AlternativeProgress; programCount: number; onCompare: () => void }) {
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
                  ? "Your recommended plan is ready. Course-rule links unlock when the optimizer finishes the comparison strategies."
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
            <>
              <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-primary/10" aria-hidden="true">
                <div className="optimization-progress-sweep h-full w-2/5 rounded-full bg-gradient-to-r from-primary via-ring to-gold" />
              </div>
              <OptimizationWorkflow elapsedSeconds={elapsedSeconds} programCount={programCount} mode="alternatives" />
            </>
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

/** Let the student request only the comparison strategies they care about. */
function AlternativePlanDialog({ open, pending, programCount, onOpenChange, onGenerate }: {
  open: boolean
  pending: boolean
  programCount: number
  onOpenChange: (open: boolean) => void
  onGenerate: (objectiveTypes: OptimizationObjectiveType[]) => Promise<void>
}) {
  const available = ALTERNATIVE_STRATEGIES.filter((objective) => objective !== "MAX_REQUIREMENT_OVERLAP" || programCount > 1)
  const [selected, setSelected] = useState<OptimizationObjectiveType[]>(["BALANCED_WORKLOAD"])
  /** Toggle one optimization strategy in the requested alternative set. */
  function toggle(objective: OptimizationObjectiveType) {
    setSelected((current) => current.includes(objective) ? current.filter((item) => item !== objective) : [...current, objective])
  }
  /** Close the picker and start generating the selected strategies. */
  function submit() {
    if (selected.length === 0 || pending) return
    onOpenChange(false)
    void onGenerate(selected)
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Generate alternative plans</DialogTitle>
          <DialogDescription>Select only the strategies you want to compare. Each selected strategy runs independently and may take additional time.</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          {available.map((objective) => {
            const label = OBJECTIVE_LABELS[objective]
            return (
              <label key={objective} className="flex cursor-pointer items-start gap-3 rounded-xl border bg-background/55 p-3 hover:bg-accent/25">
                <input type="checkbox" checked={selected.includes(objective)} onChange={() => toggle(objective)} className="mt-1 size-4 accent-primary" />
                <span><span className="block text-sm font-semibold">{label.title}</span><span className="block text-xs leading-relaxed text-muted-foreground">{label.description}</span></span>
              </label>
            )
          })}
        </div>
        <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
          <TriangleAlert className="mt-0.5 size-4 shrink-0" />
          <p>Course prerequisite links are temporarily blocked while these alternatives run. Your recommended schedule remains visible and unchanged.</p>
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button type="button" onClick={submit} disabled={selected.length === 0 || pending}><GitCompareArrows className="size-4" />Generate selected</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

interface PlanResultTabsProps extends PlansContentProps {
  activeTab: string
  onTabChange: (value: string) => void
  onOpenAlternativeDialog: () => void
}

/** Render recommended, comparison, and requirement-coverage tabs. */
function PlanResultTabs(props: PlanResultTabsProps) {
  return (
    <Tabs id="plan-result-tabs" value={props.activeTab} onValueChange={props.onTabChange} className="scroll-mt-36 gap-0">
      <div className="glass-raised sticky top-[4.5rem] z-30 rounded-xl border-primary/20 p-2 shadow-md backdrop-blur-xl">
        <TabsList className="grid h-auto! w-full grid-cols-3 gap-1 rounded-lg bg-primary/7 p-1">
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
        <PlanBoard plan={props.recommendedPlan} courseDetailsDisabled={props.alternativeGenerationPending} onPlanUpdated={props.onPlanUpdated} />
      </TabsContent>
      <TabsContent value="compare" className="space-y-4 pt-6">
        {props.plans.length > 1 ? (
          <PlanComparisonTable planIds={props.plans.map((plan) => plan.degree_plan_id)} onViewPlan={props.onSelectComparePlan} />
        ) : (
          <EmptyState icon={GitCompareArrows} title="No alternative plans yet" description="Choose the strategy you want to explore. The recommended schedule stays available while that comparison plan is generated." action={<Button type="button" onClick={props.onOpenAlternativeDialog} disabled={props.alternativeGenerationPending}><GitCompareArrows className="size-4" />Generate an alternative</Button>} />
        )}
        {props.compareBoardPlan ? (
          <div className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-sm font-semibold text-muted-foreground">{planLabel(props.compareBoardPlan)} -- full schedule</h2>
              <Button variant="ghost" size="sm" onClick={() => props.onSelectComparePlan(null)}><X className="size-4" />Close</Button>
            </div>
            <PlanBoard plan={props.compareBoardPlan} courseDetailsDisabled={props.alternativeGenerationPending} onPlanUpdated={props.onPlanUpdated} />
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

/** Combine persisted and newly generated plans without duplicating rows after refetches. */
function mergePlans(persisted: DegreePlanOut[] | undefined, alternatives: DegreePlanOut[] | undefined): DegreePlanOut[] | undefined {
  if (!persisted) return undefined
  const plansById = new Map(persisted.map((plan) => [plan.degree_plan_id, plan]))
  for (const plan of alternatives ?? []) plansById.set(plan.degree_plan_id, plan)
  return orderPlansForDisplay([...plansById.values()])
}
