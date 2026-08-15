import { Search } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { EmptyState } from "@/components/shared/empty-state"
import type { ProgramOut, ProgramType } from "@/lib/types"
import { cn } from "@/lib/utils"

const PROGRAM_TYPE_OPTIONS: { value: ProgramType | "ALL"; label: string }[] = [
  { value: "ALL", label: "All program types" },
  { value: "MAJOR", label: "Majors" },
  { value: "MINOR", label: "Minors" },
  { value: "EMPHASIS", label: "Emphases" },
  { value: "CERTIFICATE", label: "Certificates" },
  { value: "UNIVERSITY_CORE", label: "University core" },
]

interface CatalogProgramListProps {
  programs: ProgramOut[]
  search: string
  onSearchChange: (value: string) => void
  programType: ProgramType | "ALL"
  onProgramTypeChange: (value: ProgramType | "ALL") => void
  selectedProgramId: number | null
  onSelectProgram: (programId: number) => void
}

/** Search box, program-type filter, and the resulting scrollable list of
 * program cards -- the left-hand column of the catalog browser. */
export function CatalogProgramList({
  programs,
  search,
  onSearchChange,
  programType,
  onProgramTypeChange,
  selectedProgramId,
  onSelectProgram,
}: CatalogProgramListProps) {
  const filtered = filterPrograms(programs, search, programType)
  return (
    <div className="flex h-full flex-col gap-3">
      <div className="relative">
        <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
        <Input
          value={search}
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder="Search programs by name or code…"
          className="pl-9"
        />
      </div>
      <Select value={programType} onValueChange={(value) => onProgramTypeChange(value as ProgramType | "ALL")}>
        <SelectTrigger className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {PROGRAM_TYPE_OPTIONS.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <p className="text-xs text-muted-foreground">
        {filtered.length} program{filtered.length === 1 ? "" : "s"}
      </p>
      <div className="flex-1 space-y-2 overflow-y-auto pr-1">
        {filtered.length === 0 ? (
          <EmptyState icon={Search} title="No programs found" description="Try a different search term or program type." />
        ) : (
          filtered.map((program) => (
            <ProgramListCard
              key={program.academic_program_id}
              program={program}
              isSelected={program.academic_program_id === selectedProgramId}
              onSelect={() => onSelectProgram(program.academic_program_id)}
            />
          ))
        )}
      </div>
    </div>
  )
}

/** Filter and sort the catalog's programs by free-text search and program type. */
function filterPrograms(programs: ProgramOut[], search: string, programType: ProgramType | "ALL"): ProgramOut[] {
  const needle = search.trim().toLowerCase()
  return programs
    .filter((program) => programType === "ALL" || program.program_type === programType)
    .filter(
      (program) =>
        needle.length === 0 ||
        program.program_name.toLowerCase().includes(needle) ||
        program.program_code.toLowerCase().includes(needle),
    )
    .sort((a, b) => a.program_name.localeCompare(b.program_name))
}

/** One selectable program row: name, code, type badge, and total credit hours. */
function ProgramListCard({
  program,
  isSelected,
  onSelect,
}: {
  program: ProgramOut
  isSelected: boolean
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "w-full rounded-lg border p-3 text-left transition-colors",
        isSelected ? "border-primary bg-primary/5" : "border-border/60 bg-background/40 hover:bg-accent/40",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-medium">{program.program_name}</p>
        <Badge variant="outline" className="shrink-0">
          {program.program_type}
        </Badge>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        {program.program_code}
        {program.department_name ? ` · ${program.department_name}` : ""}
        {program.total_credit_hours ? ` · ${program.total_credit_hours} cr` : ""}
      </p>
    </button>
  )
}
