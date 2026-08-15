import { Building2, Check, Layers } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ErrorState } from "@/components/shared/error-state"
import { LoadingState } from "@/components/shared/loading-state"
import { useCollegesQuery } from "@/hooks/use-colleges"
import { useProgramsQuery } from "@/hooks/use-programs"
import { useScenarioBuilder } from "@/state/scenario-builder-context"
import type { ProgramOut } from "@/lib/types"
import { cn } from "@/lib/utils"

/** Step 1: pick the school (college) whose programs the rest of the wizard offers.
 * `colleges` and `departments.college_id` have been loaded since Phase 1 but were
 * never surfaced, so the program picker used to list all 147 programs at once. */
export function StepSchoolSelection() {
  const { draft, dispatch } = useScenarioBuilder()
  const collegesQuery = useCollegesQuery()
  const programsQuery = useProgramsQuery()
  if (collegesQuery.isPending || programsQuery.isPending) {
    return <LoadingState label="Loading schools…" />
  }
  if (collegesQuery.isError || programsQuery.isError) {
    return (
      <ErrorState
        message="Couldn't load the list of schools from the server."
        onRetry={() => {
          void collegesQuery.refetch()
          void programsQuery.refetch()
        }}
      />
    )
  }
  const programs = programsQuery.data
  return (
    <Card>
      <CardHeader>
        <CardTitle>Which school are you in?</CardTitle>
        <CardDescription>
          This narrows the program list on the next step. You can always choose "All schools" if you're not sure.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="grid gap-3 sm:grid-cols-2">
          {collegesQuery.data.map((college) => (
            <li key={college.college_id}>
              <SchoolOption
                title={college.college_name}
                code={college.college_code}
                counts={countPrograms(programs, college.college_id)}
                isSelected={draft.collegeId === college.college_id}
                onSelect={() => dispatch({ type: "SET_COLLEGE", collegeId: college.college_id })}
              />
            </li>
          ))}
          <li>
            <SchoolOption
              title="All schools"
              code="Browse the entire catalog"
              counts={countPrograms(programs, null)}
              icon={Layers}
              isSelected={draft.collegeId === null && draft.primaryProgramId !== null}
              onSelect={() => dispatch({ type: "SET_COLLEGE", collegeId: null })}
            />
          </li>
        </ul>
      </CardContent>
    </Card>
  )
}

interface ProgramCounts {
  majors: number
  minors: number
  emphases: number
}

/** Count the majors/minors/emphases available in one college (or all, when null). */
function countPrograms(programs: ProgramOut[], collegeId: number | null): ProgramCounts {
  const scoped = collegeId === null ? programs : programs.filter((p) => p.college_id === collegeId)
  return {
    majors: scoped.filter((p) => p.program_type === "MAJOR").length,
    minors: scoped.filter((p) => p.program_type === "MINOR").length,
    emphases: scoped.filter((p) => p.program_type === "EMPHASIS").length,
  }
}

interface SchoolOptionProps {
  title: string
  code: string
  counts: ProgramCounts
  isSelected: boolean
  onSelect: () => void
  icon?: typeof Building2
}

/** One selectable school card, showing what's on offer inside it. */
function SchoolOption({ title, code, counts, isSelected, onSelect, icon: Icon = Building2 }: SchoolOptionProps) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={isSelected}
      className={cn(
        "glass-inset glass-interactive flex h-full w-full flex-col gap-3 rounded-xl p-4 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring",
        isSelected && "border-gold ring-2 ring-gold/35",
      )}
    >
      <div className="flex items-start gap-3">
        <span
          className={cn(
            "flex size-9 shrink-0 items-center justify-center rounded-lg",
            isSelected ? "bg-gold text-gold-foreground" : "bg-primary/10 text-primary",
          )}
        >
          {isSelected ? <Check className="size-4" aria-hidden="true" /> : <Icon className="size-4" aria-hidden="true" />}
        </span>
        <span className="min-w-0">
          <span className="block text-sm font-semibold">{title}</span>
          <span className="block text-xs text-muted-foreground">{code}</span>
        </span>
      </div>
      <div className="flex flex-wrap gap-1.5">
        <Badge variant="secondary" className="font-mono text-[0.7rem]">
          {counts.majors} majors
        </Badge>
        <Badge variant="secondary" className="font-mono text-[0.7rem]">
          {counts.minors} minors
        </Badge>
        <Badge variant="secondary" className="font-mono text-[0.7rem]">
          {counts.emphases} emphases
        </Badge>
      </div>
    </button>
  )
}
