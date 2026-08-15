import { BookmarkCheck, GraduationCap, Layers, Sparkles } from "lucide-react"
import type { LucideIcon } from "lucide-react"
import { Skeleton } from "@/components/ui/skeleton"
import { useScenarioProgramsQuery } from "@/hooks/use-scenario-queries"
import type { ScenarioProgramOut, ScenarioProgramRole } from "@/lib/types"
import { cn } from "@/lib/utils"

const ROLE_META: Record<ScenarioProgramRole, { label: string; icon: LucideIcon }> = {
  PRIMARY_MAJOR: { label: "Primary major", icon: GraduationCap },
  SECOND_MAJOR: { label: "Second major", icon: Layers },
  MINOR: { label: "Minor", icon: BookmarkCheck },
  EMPHASIS: { label: "Emphasis", icon: Sparkles },
}
const ROLE_ORDER: ScenarioProgramRole[] = ["PRIMARY_MAJOR", "SECOND_MAJOR", "MINOR", "EMPHASIS"]

/** Clear, always-visible confirmation of exactly which programs this scenario
 * was built for -- shown at the top of the results page so a student never
 * has to guess whether "the plan" is for the major/minor they think it is. */
export function SelectedProgramsBar({ scenarioId }: { scenarioId: number }) {
  const programsQuery = useScenarioProgramsQuery(scenarioId)
  if (programsQuery.isLoading) return <Skeleton className="h-16 w-full rounded-xl" />
  if (programsQuery.isError || !programsQuery.data || programsQuery.data.length === 0) return null
  const sorted = [...programsQuery.data].sort(
    (a, b) => ROLE_ORDER.indexOf(a.program_role) - ROLE_ORDER.indexOf(b.program_role),
  )
  return (
    <div className="glass-inset flex flex-wrap items-center gap-2 rounded-xl p-3">
      <span className="px-1 text-xs font-semibold text-muted-foreground">Planning for</span>
      {sorted.map((program) => (
        <ProgramChip key={program.scenario_program_id} program={program} />
      ))}
    </div>
  )
}

/** One "role: program name" chip, styled as the plan's headline for a
 * primary major and more subtly for every other role. */
function ProgramChip({ program }: { program: ScenarioProgramOut }) {
  const { label, icon: Icon } = ROLE_META[program.program_role]
  const isPrimary = program.program_role === "PRIMARY_MAJOR"
  return (
    <span
      className={cn(
        "flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm",
        isPrimary ? "border-gold/40 bg-gold/10 font-semibold" : "border-border/60 bg-background/40",
      )}
    >
      <Icon className={cn("size-4", isPrimary ? "text-gold" : "text-muted-foreground")} aria-hidden="true" />
      <span className="text-[0.7rem] font-medium text-muted-foreground">{label}:</span>
      {program.program_name}
    </span>
  )
}
