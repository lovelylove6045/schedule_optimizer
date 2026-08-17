import { ArrowUpRight, Search } from "lucide-react"
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

/** Present search, type filtering, and the resulting grid of program cards. */
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
      <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_15rem]">
        <div className="relative">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
          <Input
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="Search programs by name or code…"
            className="h-11 bg-background/70 pl-9"
          />
        </div>
        <Select value={programType} onValueChange={(value) => onProgramTypeChange(value as ProgramType | "ALL")}>
          <SelectTrigger className="h-11 w-full bg-background/70">
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
      </div>
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-medium text-muted-foreground">
          {filtered.length} program{filtered.length === 1 ? "" : "s"} found
        </p>
        <p className="hidden text-xs text-muted-foreground sm:block">Select a program to view requirements</p>
      </div>
      <div className="scrollbar-slim grid flex-1 auto-rows-min grid-cols-1 gap-3 overflow-y-auto pr-1 md:grid-cols-2">
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

interface ProgramListCardProps {
  program: ProgramOut
  isSelected: boolean
  onSelect: () => void
}

/** Render one selectable program summary that opens its full details. */
function ProgramListCard({ program, isSelected, onSelect }: ProgramListCardProps) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={isSelected}
      className={cn(
        "group flex min-h-28 w-full flex-col justify-between rounded-xl border p-4 text-left transition-all hover:-translate-y-0.5 hover:shadow-md",
        isSelected ? "border-primary bg-primary/8 shadow-sm" : "border-border/60 bg-background/45 hover:border-primary/35 hover:bg-background/70",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-semibold leading-snug">{program.program_name}</p>
        <Badge variant="outline" className="shrink-0 bg-background/60">
          {program.program_type}
        </Badge>
      </div>
      <div className="mt-3 flex items-end justify-between gap-3">
        <p className="text-xs leading-relaxed text-muted-foreground">
          {program.program_code}
          {program.department_name ? ` · ${program.department_name}` : ""}
          {program.total_credit_hours ? ` · ${program.total_credit_hours} cr` : ""}
        </p>
        <ArrowUpRight className="size-4 shrink-0 text-muted-foreground transition-colors group-hover:text-primary" aria-hidden="true" />
      </div>
    </button>
  )
}
