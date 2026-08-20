import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react"
import {
  ArrowRight,
  BookOpenCheck,
  CalendarDays,
  Check,
  Clock3,
  GitMerge,
  GraduationCap,
  Layers3,
  Network,
  Route,
  SlidersHorizontal,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

interface IntroStageDefinition {
  duration: number
  label: string
}

interface PathfinderIntroProps {
  onExitStart: () => void
  onComplete: () => void
}

const INTRO_STAGES: IntroStageDefinition[] = [
  { duration: 2200, label: "Product identity" },
  { duration: 2100, label: "The planning problem" },
  { duration: 2200, label: "Connecting the path" },
  { duration: 2200, label: "Adding academic constraints" },
  { duration: 2400, label: "Optimized degree plan" },
]
const INTRO_DURATION_MS = INTRO_STAGES.reduce((total, stage) => total + stage.duration, 0)
const EXIT_DURATION_MS = 420

/** Present the deterministic product introduction and then uncover the mounted application. */
export function PathfinderIntro({ onExitStart, onComplete }: PathfinderIntroProps) {
  const skipButtonRef = useRef<HTMLButtonElement>(null)
  const { stageIndex, exiting, exit } = useIntroSequence(onExitStart, onComplete)
  /** Skip the sequence idempotently and return keyboard focus to the application. */
  function handleSkip(): void {
    const shouldMoveFocus = document.activeElement === skipButtonRef.current
    exit()
    if (shouldMoveFocus) {
      window.requestAnimationFrame(() => document.querySelector<HTMLElement>("[data-app-main]")?.focus())
    }
  }
  const progressStyle = { "--intro-progress": `${((stageIndex + 1) / INTRO_STAGES.length) * 100}%` } as CSSProperties
  return (
    <div
      className={cn("pathfinder-intro", exiting && "pathfinder-intro-exiting")}
      role="dialog"
      aria-modal={!exiting}
      aria-label="Introduction to Degree Pathfinder"
    >
      <div className="pathfinder-intro-aurora" aria-hidden="true" />
      <div className="pathfinder-intro-grid" aria-hidden="true" />
      <div className="pathfinder-intro-brand" aria-hidden="true">
        <span className="pathfinder-intro-brand-mark"><GraduationCap /></span>
        <span>Academic Degree Optimization Engine</span>
      </div>
      <main className="pathfinder-intro-stage-frame">
        <section
          className={cn("pathfinder-intro-stage", stageIndex === 0 ? "pathfinder-intro-stage-active" : "pathfinder-intro-stage-past")}
          aria-hidden={stageIndex !== 0}
        >
          <IdentityStage />
        </section>
        <section
          className={cn("pathfinder-intro-stage", "pathfinder-intro-flow-stage", stageIndex > 0 ? "pathfinder-intro-stage-active" : "pathfinder-intro-stage-future")}
          aria-hidden={stageIndex === 0}
          aria-live="polite"
        >
          <PathwayFlow step={Math.max(0, stageIndex - 1)} />
        </section>
      </main>
      <div className="pathfinder-intro-progress" aria-label={`Introduction step ${stageIndex + 1} of ${INTRO_STAGES.length}`}>
        <div className="pathfinder-intro-progress-track"><span style={progressStyle} /></div>
        <span>{INTRO_STAGES[stageIndex].label}</span>
      </div>
      <Button
        ref={skipButtonRef}
        type="button"
        variant="ghost"
        className="pathfinder-intro-skip"
        onClick={handleSkip}
        disabled={exiting}
      >
        Skip Intro <ArrowRight className="size-4" />
      </Button>
    </div>
  )
}

/** Advance intro stages, clean up every timer, and provide one race-safe exit action. */
function useIntroSequence(onExitStart: () => void, onComplete: () => void) {
  const [stageIndex, setStageIndex] = useState(0)
  const [exiting, setExiting] = useState(false)
  const exitStartedRef = useRef(false)
  const exitTimerRef = useRef<number | null>(null)
  const exit = useCallback(() => {
    if (exitStartedRef.current) return
    exitStartedRef.current = true
    setExiting(true)
    onExitStart()
    exitTimerRef.current = window.setTimeout(onComplete, EXIT_DURATION_MS)
  }, [onComplete, onExitStart])
  useEffect(() => {
    let elapsed = 0
    const stageTimers = INTRO_STAGES.slice(0, -1).map((stage, index) => {
      elapsed += stage.duration
      return window.setTimeout(() => setStageIndex(index + 1), elapsed)
    })
    const automaticExitTimer = window.setTimeout(exit, INTRO_DURATION_MS)
    return () => {
      stageTimers.forEach(window.clearTimeout)
      window.clearTimeout(automaticExitTimer)
      if (exitTimerRef.current !== null) window.clearTimeout(exitTimerRef.current)
    }
  }, [exit])
  return { stageIndex, exiting, exit }
}

/** Introduce the product using the existing graduation-cap mark and brand palette. */
function IdentityStage() {
  return (
    <div className="pathfinder-intro-copy pathfinder-intro-identity">
      <span className="pathfinder-intro-hero-mark" aria-hidden="true"><GraduationCap /></span>
      <p className="pathfinder-intro-eyebrow">Stellic Pathfinders</p>
      <h1>Degree Pathfinder</h1>
      <p>Optimization-driven academic planning</p>
    </div>
  )
}

/** Build one persistent planning flow whose earlier ideas remain visible. */
function PathwayFlow({ step }: { step: number }) {
  return (
    <div className="pathfinder-intro-flow">
      <header className="pathfinder-intro-flow-heading">
        <p className="pathfinder-intro-eyebrow">The planning challenge</p>
        <h2>A degree is more than a checklist.</h2>
        <p>Every course shapes the path that follows.</p>
      </header>
      <div className="pathfinder-intro-flow-track">
        <FlowInputs />
        <FlowConnector active={step >= 1} />
        <OptimizationCore active={step >= 1} expanded={step >= 2} />
        <FlowConnector active={step >= 3} />
        <FlowResult active={step >= 3} />
      </div>
      <ConstraintRow active={step >= 2} />
    </div>
  )
}

/** Show the core academic decisions entering the planning flow. */
function FlowInputs() {
  const inputs = [[Layers3, "Requirements"], [BookOpenCheck, "Prerequisites"], [Clock3, "Timing"], [GitMerge, "Electives"]] as const
  return (
    <div className="pathfinder-intro-flow-card pathfinder-intro-flow-input-card">
      <span className="pathfinder-intro-flow-label">Academic decisions</span>
      <div className="pathfinder-intro-flow-input-grid">
        {inputs.map(([Icon, label]) => <span key={label}><Icon aria-hidden="true" />{label}</span>)}
      </div>
    </div>
  )
}

/** Draw a directional connection when the next part of the model becomes active. */
function FlowConnector({ active }: { active: boolean }) {
  return (
    <div className={cn("pathfinder-intro-flow-connector", active && "pathfinder-intro-revealed")} aria-hidden="true">
      <span /><ArrowRight />
    </div>
  )
}

/** Reveal the whole-path optimization engine at the center of the composition. */
function OptimizationCore({ active, expanded }: { active: boolean; expanded: boolean }) {
  return (
    <div className={cn("pathfinder-intro-flow-card", "pathfinder-intro-engine-card", active && "pathfinder-intro-revealed", expanded && "pathfinder-intro-engine-expanded")} aria-hidden={!active}>
      <span className="pathfinder-intro-engine-icon"><Network aria-hidden="true" /></span>
      <span className="pathfinder-intro-flow-label">Whole-path optimization</span>
      <h3>Optimize the entire path</h3>
      <p>Academically valid pathways that make better use of every course.</p>
    </div>
  )
}

/** Add the structured program and student constraints without replacing prior content. */
function ConstraintRow({ active }: { active: boolean }) {
  const constraints = [[Layers3, "Major + Minor"], [CalendarDays, "Course Offerings"], [SlidersHorizontal, "Student Constraints"], [GitMerge, "Requirement Overlap"]] as const
  return (
    <div className={cn("pathfinder-intro-constraint-row", active && "pathfinder-intro-revealed")} aria-hidden={!active}>
      {constraints.map(([Icon, label]) => <span key={label}><Icon aria-hidden="true" />{label}</span>)}
    </div>
  )
}

/** Finish the cumulative flow with the optimized plan and restrained closing line. */
function FlowResult({ active }: { active: boolean }) {
  return (
    <div className={cn("pathfinder-intro-flow-card", "pathfinder-intro-result-card", active && "pathfinder-intro-revealed")} aria-hidden={!active}>
      <span className="pathfinder-intro-result-icon"><Check aria-hidden="true" /></span>
      <span className="pathfinder-intro-flow-label">Optimized Degree Plan</span>
      <h3>Explore a better path to graduation.</h3>
      <span className="pathfinder-intro-prototype-note"><Route aria-hidden="true" /> Decision-support prototype</span>
    </div>
  )
}
