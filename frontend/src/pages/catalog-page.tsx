import { useState } from "react"
import { Landmark } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { ErrorState } from "@/components/shared/error-state"
import { LoadingState } from "@/components/shared/loading-state"
import { CatalogProgramDetail } from "@/components/catalog/catalog-program-detail"
import { CatalogProgramList } from "@/components/catalog/catalog-program-list"
import { CatalogSnapshotNotice } from "@/components/catalog/catalog-snapshot-notice"
import { useCollegesQuery } from "@/hooks/use-colleges"
import { useProgramsQuery } from "@/hooks/use-programs"
import type { ProgramType } from "@/lib/types"
import { cn } from "@/lib/utils"

/** Read-only catalog browser: every college and every academic program (with
 * its full requirement tree) straight from the loaded `schedule_optimizer_db`
 * data, for students exploring "what's out there" before building a scenario. */
export function CatalogPage() {
  const collegesQuery = useCollegesQuery()
  const programsQuery = useProgramsQuery()
  const [collegeId, setCollegeId] = useState<number | null>(null)
  const [search, setSearch] = useState("")
  const [programType, setProgramType] = useState<ProgramType | "ALL">("ALL")
  const [departmentId, setDepartmentId] = useState<number | null>(null)
  const [selectedProgramId, setSelectedProgramId] = useState<number | null>(null)
  if (collegesQuery.isPending || programsQuery.isPending) {
    return <LoadingState label="Loading the catalog…" rows={6} />
  }
  if (collegesQuery.isError || programsQuery.isError) {
    return <ErrorState message="Couldn't load the catalog from the server." />
  }
  const programsInCollege = programsQuery.data.filter(
    (program) =>
      (collegeId === null || program.college_id === collegeId) &&
      (departmentId === null || program.department_id === departmentId),
  )
  const departments = Array.from(
    new Map(
      programsQuery.data
        .filter((program) => collegeId === null || program.college_id === collegeId)
        .map((program) => [program.department_id, program.department_name ?? program.department_code ?? "Department"]),
    ),
  ).sort((a, b) => a[1].localeCompare(b[1]))
  const selectedProgram = programsQuery.data.find((program) => program.academic_program_id === selectedProgramId)
  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">Catalog</h1>
        <p className="text-muted-foreground">
          Browse every college, program, and requirement in the catalog before you start planning.
        </p>
      </div>
      <CatalogSnapshotNotice />
      <CollegeFilterBar
        colleges={collegesQuery.data}
        totalProgramCount={programsQuery.data.length}
        selectedCollegeId={collegeId}
        onSelectCollege={(nextCollegeId) => {
          setCollegeId(nextCollegeId)
          setDepartmentId(null)
        }}
      />
      <select
        aria-label="Filter by department"
        className="h-9 rounded-md border bg-background px-3 text-sm"
        value={departmentId ?? "ALL"}
        onChange={(event) => setDepartmentId(event.target.value === "ALL" ? null : Number(event.target.value))}
      >
        <option value="ALL">All departments</option>
        {departments.map(([id, name]) => (
          <option key={id} value={id}>{name}</option>
        ))}
      </select>
      <div className="grid gap-4 lg:grid-cols-[22rem_1fr]">
        <div className="glass-panel h-[36rem] rounded-xl p-4">
          <CatalogProgramList
            programs={programsInCollege}
            search={search}
            onSearchChange={setSearch}
            programType={programType}
            onProgramTypeChange={setProgramType}
            selectedProgramId={selectedProgramId}
            onSelectProgram={setSelectedProgramId}
          />
        </div>
        <div className="glass-panel min-h-[36rem] rounded-xl p-4">
          <CatalogProgramDetail program={selectedProgram} />
        </div>
      </div>
    </div>
  )
}

/** Pill row for narrowing the program list to one college (or "All schools"). */
function CollegeFilterBar({
  colleges,
  totalProgramCount,
  selectedCollegeId,
  onSelectCollege,
}: {
  colleges: { college_id: number; college_code: string; college_name: string }[]
  totalProgramCount: number
  selectedCollegeId: number | null
  onSelectCollege: (collegeId: number | null) => void
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <CollegePill
        label="All schools"
        count={totalProgramCount}
        isSelected={selectedCollegeId === null}
        onClick={() => onSelectCollege(null)}
      />
      {colleges.map((college) => (
        <CollegePill
          key={college.college_id}
          label={college.college_name}
          isSelected={selectedCollegeId === college.college_id}
          onClick={() => onSelectCollege(college.college_id)}
        />
      ))}
    </div>
  )
}

/** One college filter pill, styled as a selected/unselected toggle button. */
function CollegePill({
  label,
  count,
  isSelected,
  onClick,
}: {
  label: string
  count?: number
  isSelected: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm transition-colors",
        isSelected
          ? "border-primary bg-primary text-primary-foreground"
          : "border-border/60 bg-background/40 hover:bg-accent/40",
      )}
    >
      <Landmark className="size-3.5" aria-hidden="true" />
      {label}
      {count !== undefined ? (
        <Badge variant={isSelected ? "secondary" : "outline"} className="ml-0.5">
          {count}
        </Badge>
      ) : null}
    </button>
  )
}
