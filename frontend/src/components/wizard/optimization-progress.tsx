import { useEffect, useState } from "react"
import { BrainCircuit, CalendarRange, ListChecks, Sparkles } from "lucide-react"
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog"

export type OptimizationPhase = "preparing" | "solving"

interface OptimizationProgressProps {
  phase: OptimizationPhase
}

const SOLVER_MESSAGES = [
  { afterSeconds: 0, text: "Starting the scheduling engine and loading your planning rules…" },
  { afterSeconds: 8, text: "Exploring course combinations that satisfy your requirements…" },
  { afterSeconds: 20, text: "Checking prerequisites, term availability, and credit limits…" },
  { afterSeconds: 40, text: "Comparing schedules against your ranked priorities…" },
  { afterSeconds: 70, text: "Still searching—tight constraints can take a little longer." },
  { afterSeconds: 120, text: "The optimizer is still active and refining the strongest valid plan." },
]

/** Keep users informed while the long-running optimizer request remains active. */
export function OptimizationProgress({ phase }: OptimizationProgressProps) {
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  useEffect(() => {
    const startedAt = Date.now()
    const timer = window.setInterval(() => setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000)), 1000)
    return () => window.clearInterval(timer)
  }, [])
  const message = phase === "preparing" ? "Saving your scenario and preparing the optimization request…" : solverMessage(elapsedSeconds)
  return (
    <Dialog open>
      <DialogContent
        showCloseButton={false}
        onEscapeKeyDown={(event) => event.preventDefault()}
        onPointerDownOutside={(event) => event.preventDefault()}
        className="max-w-xl overflow-hidden rounded-3xl p-6 text-center sm:max-w-xl sm:p-8"
        aria-busy="true"
      >
        <div className="optimization-pattern absolute inset-0 opacity-45" aria-hidden="true" />
        <div className="relative">
          <OptimizationOrb />
          <p className="mt-5 text-xs font-semibold tracking-[0.18em] text-primary uppercase">Optimizer active</p>
          <DialogTitle className="mt-2 text-2xl font-bold tracking-tight">Building your degree plan</DialogTitle>
          <DialogDescription className="mx-auto mt-2 max-w-md text-sm text-muted-foreground" role="status" aria-live="polite">
            {message}
          </DialogDescription>
          <IndeterminateProgress />
          <OptimizationActivities />
          <div className="mt-6 flex flex-col items-center justify-between gap-2 border-t pt-4 text-xs text-muted-foreground sm:flex-row">
            <p>Keep this tab open—you’ll be taken to your results automatically.</p>
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

/** Summarize the kinds of work being performed during optimization. */
function OptimizationActivities() {
  const activities = [
    { icon: ListChecks, label: "Requirements" },
    { icon: CalendarRange, label: "Schedules" },
    { icon: Sparkles, label: "Priorities" },
  ]
  return (
    <ul className="mt-5 grid grid-cols-3 gap-2">
      {activities.map(({ icon: Icon, label }, index) => (
        <li key={label} className="optimization-activity flex flex-col items-center gap-1.5 rounded-xl border bg-background/45 px-2 py-3" style={{ animationDelay: `${index * 450}ms` }}>
          <Icon className="size-4 text-primary" aria-hidden="true" />
          <span className="text-xs font-medium">{label}</span>
        </li>
      ))}
    </ul>
  )
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
