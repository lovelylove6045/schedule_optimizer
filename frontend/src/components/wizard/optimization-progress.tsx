import { useEffect, useState } from "react"
import { BrainCircuit, CalendarRange, Check, GitMerge, ListChecks, LoaderCircle, ShieldCheck, Sparkles, X, type LucideIcon } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog"

export type OptimizationPhase = "preparing" | "solving"

interface OptimizationProgressProps {
  phase: OptimizationPhase
  onCancel?: () => void
  programCount?: number
  objectiveCount?: number
}

const SOLVER_MESSAGES = [
  { afterSeconds: 0, text: "Starting the scheduling engine and loading your planning rules…" },
  { afterSeconds: 8, text: "Exploring course combinations that satisfy your requirements…" },
  { afterSeconds: 20, text: "Checking prerequisites, term availability, and credit limits…" },
  { afterSeconds: 40, text: "Comparing schedules against your ranked priorities…" },
  { afterSeconds: 70, text: "Still searching—tight constraints can take a little longer." },
  { afterSeconds: 120, text: "The optimizer is still active and refining the strongest valid plan." },
]

interface SolverActivity {
  afterSeconds: number
  icon: LucideIcon
  label: string
  detail: string
}

interface OptimizationWorkflowProps {
  elapsedSeconds: number
  programCount?: number
  objectiveCount?: number
  mode?: "recommended" | "alternatives"
}

/** Keep users informed while the long-running optimizer request remains active. */
export function OptimizationProgress({ phase, onCancel, programCount = 1, objectiveCount = 3 }: OptimizationProgressProps) {
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  useEffect(() => {
    const startedAt = Date.now()
    const timer = window.setInterval(() => setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000)), 1000)
    return () => window.clearInterval(timer)
  }, [phase])
  const message = phase === "preparing" ? "Saving your scenario and preparing the optimization request…" : solverMessage(elapsedSeconds)
  return (
    <Dialog open>
      <DialogContent
        showCloseButton={false}
        onEscapeKeyDown={(event) => {
          event.preventDefault()
          onCancel?.()
        }}
        onPointerDownOutside={(event) => event.preventDefault()}
        className="max-w-2xl overflow-hidden rounded-3xl p-6 text-center sm:max-w-2xl sm:p-8"
        aria-busy="true"
      >
        <div className="optimization-pattern absolute inset-0 opacity-45" aria-hidden="true" />
        {onCancel ? (
          <Button type="button" variant="ghost" size="icon" onClick={onCancel} className="absolute top-4 right-4 z-10 rounded-full" aria-label="Cancel plan generation" title="Cancel plan generation">
            <X className="size-4" aria-hidden="true" />
          </Button>
        ) : null}
        <div className="relative">
          <OptimizationOrb />
          <p className="mt-5 text-xs font-semibold tracking-[0.18em] text-primary uppercase">Optimizer active</p>
          <DialogTitle className="mt-2 text-2xl font-bold tracking-tight">Building your degree plan</DialogTitle>
          <DialogDescription className="mx-auto mt-2 max-w-md text-sm text-muted-foreground" role="status" aria-live="polite">
            {message}
          </DialogDescription>
          <IndeterminateProgress />
          <OptimizationWorkflow elapsedSeconds={phase === "preparing" ? 0 : elapsedSeconds} programCount={programCount} objectiveCount={objectiveCount} />
          <div className="mt-6 flex flex-col items-center justify-between gap-2 border-t pt-4 text-xs text-muted-foreground sm:flex-row">
            <p>{onCancel ? "Keep this tab open, or use the close button to cancel and return to Review." : "Keep this tab open while the optimizer finishes this run."}</p>
            <p className="shrink-0 font-mono text-foreground" aria-label={`Elapsed time ${formatElapsedTime(elapsedSeconds)}`}>
              {formatElapsedTime(elapsedSeconds)} elapsed
            </p>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

/** Render an animated solver mark without implying measurable percent completion. */
function OptimizationOrb() {
  return (
    <div className="relative mx-auto flex size-24 items-center justify-center" aria-hidden="true">
      <span className="absolute inset-0 rounded-full border border-primary/15 border-t-primary/80 motion-safe:animate-spin [animation-duration:2.4s]" />
      <span className="absolute inset-2 rounded-full border border-gold/20 border-b-gold motion-safe:animate-spin [animation-direction:reverse] [animation-duration:3.2s]" />
      <span className="flex size-14 items-center justify-center rounded-2xl bg-primary text-primary-foreground shadow-lg shadow-primary/20">
        <BrainCircuit className="size-7 motion-safe:animate-pulse" />
      </span>
      <span className="absolute top-1 right-3 size-2.5 rounded-full bg-gold motion-safe:animate-ping" />
    </div>
  )
}

/** Display an animated track that communicates activity without a false percentage. */
function IndeterminateProgress() {
  return (
    <div className="mt-6 h-2 overflow-hidden rounded-full bg-primary/10" aria-hidden="true">
      <div className="optimization-progress-sweep h-full w-2/5 rounded-full bg-gradient-to-r from-primary via-ring to-gold" />
    </div>
  )
}

/** Highlight expected recommended or alternative passes without claiming exact completion. */
export function OptimizationWorkflow({ elapsedSeconds, programCount = 1, objectiveCount = 3, mode = "recommended" }: OptimizationWorkflowProps) {
  const activities = mode === "alternatives" ? buildAlternativeActivities(programCount) : buildSolverActivities(programCount, objectiveCount)
  const activeIndex = currentActivityIndex(activities, elapsedSeconds)
  const activeActivity = activities[activeIndex]
  return (
    <div className="mt-5">
      <ul className="grid grid-cols-2 gap-2 md:grid-cols-4" aria-label="Expected optimization workflow">
        {activities.map(({ icon: Icon, label }, index) => (
          <li key={label} className={activityClassName(index, activeIndex)}>
            <span className={activityIconClassName(index, activeIndex)}>
              {index < activeIndex ? <Check className="size-3.5" aria-hidden="true" /> : index === activeIndex ? <LoaderCircle className="size-3.5 motion-safe:animate-spin" aria-hidden="true" /> : <Icon className="size-3.5" aria-hidden="true" />}
            </span>
            <span className="min-w-0 whitespace-normal text-left text-[0.68rem] leading-tight font-semibold sm:text-xs">{label}</span>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-xs font-medium text-foreground" role="status" aria-live="polite">Current expected pass: {activeActivity.detail}</p>
      <p className="mt-1 text-[0.68rem] text-muted-foreground">The indicator follows the expected workflow. Solver passes can overlap or repeat before the result is ready.</p>
    </div>
  )
}

/** Build the expected passes used while distinct comparison plans are generated. */
function buildAlternativeActivities(programCount: number): SolverActivity[] {
  const normalizedPrograms = Math.max(1, programCount)
  const activities: Omit<SolverActivity, "afterSeconds">[] = [
    { icon: BrainCircuit, label: "Prepare search", detail: "Preparing independent comparison strategies" },
  ]
  if (normalizedPrograms > 1) activities.push({ icon: GitMerge, label: "Program overlap", detail: "Rechecking overlap across selected programs" })
  activities.push({ icon: Sparkles, label: "Credit strategy", detail: "Searching for a credit-efficient alternative" })
  activities.push({ icon: CalendarRange, label: "Graduation strategy", detail: "Searching for a graduation-focused alternative" })
  activities.push({ icon: ListChecks, label: "Workload strategy", detail: "Searching for a balanced-workload alternative" })
  activities.push({ icon: ShieldCheck, label: "Distinct plans", detail: "Removing duplicate and equivalent schedules" })
  activities.push({ icon: ShieldCheck, label: "Final checks", detail: "Finalizing the strongest distinct comparisons" })
  return activities.map((activity, index) => ({ ...activity, afterSeconds: activityStartSeconds(index, activities.length, normalizedPrograms) }))
}

/** Build a workflow whose visible stages grow with scenario complexity. */
function buildSolverActivities(programCount: number, objectiveCount: number): SolverActivity[] {
  const normalizedPrograms = Math.max(1, programCount)
  const normalizedObjectives = Math.max(1, objectiveCount)
  const activities: Omit<SolverActivity, "afterSeconds">[] = [
    { icon: BrainCircuit, label: "Setup", detail: "Building the planning model" },
    { icon: ListChecks, label: "Primary program", detail: "Mapping the primary program requirements" },
  ]
  if (normalizedPrograms > 1) activities.push({ icon: ListChecks, label: `${normalizedPrograms - 1} additional`, detail: `Mapping ${normalizedPrograms - 1} additional selected program${normalizedPrograms === 2 ? "" : "s"}` })
  if (normalizedPrograms > 1) activities.push({ icon: GitMerge, label: "Shared courses", detail: "Finding courses shared across selected programs" })
  activities.push({ icon: ShieldCheck, label: "Constraints", detail: "Checking prerequisites and course restrictions" })
  activities.push({ icon: CalendarRange, label: "Schedule", detail: "Placing courses into valid academic terms" })
  activities.push({ icon: Sparkles, label: `${normalizedObjectives} priorities`, detail: `Optimizing ${normalizedObjectives} ranked planning priorit${normalizedObjectives === 1 ? "y" : "ies"}` })
  activities.push({ icon: ShieldCheck, label: "Final checks", detail: "Verifying and refining the strongest plan" })
  return activities.map((activity, index) => ({ ...activity, afterSeconds: activityStartSeconds(index, activities.length, normalizedPrograms) }))
}

/** Space expected pass transitions while leaving final verification unbounded. */
function activityStartSeconds(index: number, activityCount: number, programCount: number): number {
  if (index === 0) return 0
  const finalIndex = activityCount - 1
  const interval = programCount > 1 ? 11 : 9
  return index === finalIndex ? (finalIndex * interval) + 12 : index * interval
}

/** Return the activity tile that best reflects elapsed optimization time. */
function currentActivityIndex(activities: SolverActivity[], elapsedSeconds: number): number {
  return activities.reduce((activeIndex, activity, index) => elapsedSeconds >= activity.afterSeconds ? index : activeIndex, 0)
}

/** Return styling for completed, current, and upcoming workflow stages. */
function activityClassName(index: number, activeIndex: number): string {
  if (index < activeIndex) return "flex min-h-11 min-w-0 items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-2.5 py-2 text-emerald-800"
  if (index === activeIndex) return "flex min-h-11 min-w-0 items-center gap-2 rounded-xl border border-primary/35 bg-primary/10 px-2.5 py-2 text-primary shadow-sm"
  return "flex min-h-11 min-w-0 items-center gap-2 rounded-xl border bg-background/40 px-2.5 py-2 text-muted-foreground"
}

/** Return the compact status-circle style for one workflow stage. */
function activityIconClassName(index: number, activeIndex: number): string {
  if (index < activeIndex) return "flex size-6 shrink-0 items-center justify-center rounded-full bg-emerald-600 text-white"
  if (index === activeIndex) return "flex size-6 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground"
  return "flex size-6 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground"
}

/** Return the latest honest activity message for the elapsed solve time. */
function solverMessage(elapsedSeconds: number): string {
  return [...SOLVER_MESSAGES].reverse().find((message) => elapsedSeconds >= message.afterSeconds)?.text ?? SOLVER_MESSAGES[0].text
}

/** Format elapsed seconds as a compact minutes-and-seconds timer. */
function formatElapsedTime(elapsedSeconds: number): string {
  const minutes = Math.floor(elapsedSeconds / 60)
  const seconds = elapsedSeconds % 60
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`
}
