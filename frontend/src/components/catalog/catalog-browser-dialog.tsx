import { useState } from "react"
import { BookOpen } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { CatalogProgramDetail } from "@/components/catalog/catalog-program-detail"
import { CatalogProgramList } from "@/components/catalog/catalog-program-list"
import { CatalogSnapshotNotice } from "@/components/catalog/catalog-snapshot-notice"
import { ErrorState } from "@/components/shared/error-state"
import { LoadingState } from "@/components/shared/loading-state"
import { useProgramsQuery } from "@/hooks/use-programs"
import type { ProgramType } from "@/lib/types"

/** Open a reusable, lazy-detail catalog browser without leaving the current workflow. */
export function CatalogBrowserDialog() {
  const programsQuery = useProgramsQuery()
  const [search, setSearch] = useState("")
  const [programType, setProgramType] = useState<ProgramType | "ALL">("ALL")
  const [collegeId, setCollegeId] = useState<number | null>(null)
  const [departmentId, setDepartmentId] = useState<number | null>(null)
  const [selectedProgramId, setSelectedProgramId] = useState<number | null>(null)
  const selectedProgram = programsQuery.data?.find((program) => program.academic_program_id === selectedProgramId)
  const colleges = Array.from(
    new Map(
      (programsQuery.data ?? [])
        .filter((program) => program.college_id !== null)
        .map((program) => [program.college_id as number, program.college_name ?? program.college_code ?? "College"]),
    ),
  ).sort((a, b) => a[1].localeCompare(b[1]))
  const departments = Array.from(
    new Map(
      (programsQuery.data ?? [])
        .filter((program) => collegeId === null || program.college_id === collegeId)
        .map((program) => [program.department_id, program.department_name ?? program.department_code ?? "Department"]),
    ),
  ).sort((a, b) => a[1].localeCompare(b[1]))
  const filteredPrograms = (programsQuery.data ?? []).filter(
    (program) =>
      (collegeId === null || program.college_id === collegeId) &&
      (departmentId === null || program.department_id === departmentId),
  )
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <BookOpen className="size-4" aria-hidden="true" />
          Browse catalog
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] max-w-5xl overflow-hidden">
        <DialogHeader>
          <DialogTitle>Missouri S&amp;T catalog browser</DialogTitle>
        </DialogHeader>
        <CatalogSnapshotNotice />
        {programsQuery.isPending ? <LoadingState label="Loading the catalog…" /> : null}
        {programsQuery.isError ? <ErrorState message="Couldn't load the catalog." /> : null}
        {programsQuery.data ? (
          <div className="grid min-h-0 gap-4 md:grid-cols-[20rem_1fr]">
            <div className="h-[65vh] min-h-0 rounded-xl border p-3">
              <div className="mb-3 grid grid-cols-2 gap-2">
                <select
                  aria-label="Filter catalog dialog by college"
                  className="h-9 min-w-0 rounded-md border bg-background px-2 text-xs"
                  value={collegeId ?? "ALL"}
                  onChange={(event) => {
                    setCollegeId(event.target.value === "ALL" ? null : Number(event.target.value))
                    setDepartmentId(null)
                  }}
                >
                  <option value="ALL">All colleges</option>
                  {colleges.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
                </select>
                <select
                  aria-label="Filter catalog dialog by department"
                  className="h-9 min-w-0 rounded-md border bg-background px-2 text-xs"
                  value={departmentId ?? "ALL"}
                  onChange={(event) => setDepartmentId(event.target.value === "ALL" ? null : Number(event.target.value))}
                >
                  <option value="ALL">All departments</option>
                  {departments.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
                </select>
              </div>
              <CatalogProgramList
                programs={filteredPrograms}
                search={search}
                onSearchChange={setSearch}
                programType={programType}
                onProgramTypeChange={setProgramType}
                selectedProgramId={selectedProgramId}
                onSelectProgram={setSelectedProgramId}
              />
            </div>
            <div className="h-[65vh] overflow-y-auto rounded-xl border p-3">
              <CatalogProgramDetail program={selectedProgram} />
            </div>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  )
}
