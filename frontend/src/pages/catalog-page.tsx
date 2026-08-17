import { useState, type ReactNode } from "react"
import { BookOpen, Building2, SlidersHorizontal } from "lucide-react"
import { CatalogProgramDialog } from "@/components/catalog/catalog-program-dialog"
import { CatalogProgramList } from "@/components/catalog/catalog-program-list"
import { CatalogSnapshotNotice } from "@/components/catalog/catalog-snapshot-notice"
import { ErrorState } from "@/components/shared/error-state"
import { LoadingState } from "@/components/shared/loading-state"
import { useCollegesQuery } from "@/hooks/use-colleges"
import { useProgramsQuery } from "@/hooks/use-programs"
import type { ProgramOut, ProgramType } from "@/lib/types"

type FilterOption = [number, string]

/** Present the complete read-only catalog in a single, searchable workspace. */
export function CatalogPage() {
  const collegesQuery = useCollegesQuery()
  const programsQuery = useProgramsQuery()
  const [collegeId, setCollegeId] = useState<number | null>(null)
  const [departmentId, setDepartmentId] = useState<number | null>(null)
  const [search, setSearch] = useState("")
  const [programType, setProgramType] = useState<ProgramType | "ALL">("ALL")
  const [selectedProgramId, setSelectedProgramId] = useState<number | null>(null)
  const [isDetailOpen, setIsDetailOpen] = useState(false)
  if (collegesQuery.isPending || programsQuery.isPending) {
    return <LoadingState label="Loading the catalog…" rows={6} />
  }
  if (collegesQuery.isError || programsQuery.isError) {
    return <ErrorState message="Couldn't load the catalog from the server." />
  }
  const departments = getDepartmentOptions(programsQuery.data, collegeId)
  const filteredPrograms = filterProgramsBySchool(programsQuery.data, collegeId, departmentId)
  const selectedProgram = programsQuery.data.find((program) => program.academic_program_id === selectedProgramId)
  const selectProgram = (programId: number) => {
    setSelectedProgramId(programId)
    setIsDetailOpen(true)
  }
  return (
    <div className="space-y-6">
      <CatalogHeading programCount={programsQuery.data.length} />
      <CatalogSnapshotNotice />
      <section className="glass-panel overflow-hidden rounded-2xl">
        <CatalogSchoolFilters
          colleges={collegesQuery.data.map((college) => [college.college_id, college.college_name])}
          departments={departments}
          collegeId={collegeId}
          departmentId={departmentId}
          onCollegeChange={(nextCollegeId) => {
            setCollegeId(nextCollegeId)
            setDepartmentId(null)
          }}
          onDepartmentChange={setDepartmentId}
        />
        <div className="h-[42rem] p-4 sm:p-5">
          <CatalogProgramList
            programs={filteredPrograms}
            search={search}
            onSearchChange={setSearch}
            programType={programType}
            onProgramTypeChange={setProgramType}
            selectedProgramId={selectedProgramId}
            onSelectProgram={selectProgram}
          />
        </div>
      </section>
      <CatalogProgramDialog program={selectedProgram} open={isDetailOpen} onOpenChange={setIsDetailOpen} />
    </div>
  )
}

/** Introduce the catalog and summarize its available programs. */
function CatalogHeading({ programCount }: { programCount: number }) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="space-y-1">
        <p className="text-xs font-semibold tracking-[0.18em] text-primary uppercase">Academic catalog</p>
        <h1 className="text-3xl font-bold tracking-tight">Find your program</h1>
        <p className="max-w-2xl text-muted-foreground">
          Search every college, department, and program, then open any result to review its complete requirements.
        </p>
      </div>
      <div className="flex w-fit items-center gap-2 rounded-full border bg-background/45 px-3 py-1.5 text-sm text-muted-foreground">
        <BookOpen className="size-4 text-primary" aria-hidden="true" />
        <span><strong className="font-semibold text-foreground">{programCount}</strong> programs</span>
      </div>
    </div>
  )
}

interface CatalogSchoolFiltersProps {
  colleges: FilterOption[]
  departments: FilterOption[]
  collegeId: number | null
  departmentId: number | null
  onCollegeChange: (collegeId: number | null) => void
  onDepartmentChange: (departmentId: number | null) => void
}

/** Group the school-level catalog filters in a clear toolbar. */
function CatalogSchoolFilters(props: CatalogSchoolFiltersProps) {
  return (
    <div className="border-b bg-background/30 p-4 sm:p-5">
      <div className="mb-3 flex items-center gap-2">
        <SlidersHorizontal className="size-4 text-primary" aria-hidden="true" />
        <h2 className="text-sm font-semibold">Narrow the catalog</h2>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <FilterSelect
          label="College"
          allLabel="All colleges"
          icon={<Building2 className="size-4" aria-hidden="true" />}
          options={props.colleges}
          value={props.collegeId}
          onChange={props.onCollegeChange}
        />
        <FilterSelect
          label="Department"
          allLabel="All departments"
          icon={<BookOpen className="size-4" aria-hidden="true" />}
          options={props.departments}
          value={props.departmentId}
          onChange={props.onDepartmentChange}
        />
      </div>
    </div>
  )
}

interface FilterSelectProps {
  label: string
  allLabel: string
  icon: ReactNode
  options: FilterOption[]
  value: number | null
  onChange: (value: number | null) => void
}

/** Render a labeled native select for a catalog filter. */
function FilterSelect({ label, allLabel, icon, options, value, onChange }: FilterSelectProps) {
  return (
    <label className="space-y-1.5">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <span className="relative block">
        <span className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-muted-foreground">{icon}</span>
        <select
          className="h-11 w-full appearance-none rounded-lg border bg-background/70 pr-9 pl-10 text-sm outline-none transition-shadow focus:ring-2 focus:ring-ring/50"
          value={value ?? "ALL"}
          onChange={(event) => onChange(event.target.value === "ALL" ? null : Number(event.target.value))}
        >
          <option value="ALL">{allLabel}</option>
          {options.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
        </select>
        <span className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-xs text-muted-foreground">⌄</span>
      </span>
    </label>
  )
}

/** Return alphabetized departments available for the selected college. */
function getDepartmentOptions(programs: ProgramOut[], collegeId: number | null): FilterOption[] {
  return Array.from(
    new Map(
      programs
        .filter((program) => collegeId === null || program.college_id === collegeId)
        .map((program) => [program.department_id, program.department_name ?? program.department_code ?? "Department"]),
    ),
  ).sort((a, b) => a[1].localeCompare(b[1]))
}

/** Return programs belonging to the selected college and department. */
function filterProgramsBySchool(programs: ProgramOut[], collegeId: number | null, departmentId: number | null) {
  return programs.filter(
    (program) =>
      (collegeId === null || program.college_id === collegeId) &&
      (departmentId === null || program.department_id === departmentId),
  )
}
