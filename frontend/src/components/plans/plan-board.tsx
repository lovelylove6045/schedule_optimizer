import { useRef, useState } from "react"
import {
  BadgePlus,
  BookMarked,
  CalendarRange,
  CalendarX,
  Compass,
  Download,
  GraduationCap,
  Layers3,
  LayoutGrid,
  Leaf,
  ListTree,
  LoaderCircle,
  Palette,
  Sprout,
  Shuffle,
  Sun,
  Target,
  TriangleAlert,
  UsersRound,
  type LucideIcon,
} from "lucide-react"
import { toast } from "sonner"
import { AddCourseButton } from "@/components/plans/add-course-button"
import { PlanCourseCard, type PlanViewMode } from "@/components/plans/plan-course-card"
import { PlanSummaryCard } from "@/components/plans/plan-summary-card"
import { EmptyState } from "@/components/shared/empty-state"
import { ErrorState } from "@/components/shared/error-state"
import { LoadingState } from "@/components/shared/loading-state"
import { Button } from "@/components/ui/button"
import { usePlanSwapOptionsQuery } from "@/hooks/use-plan-queries"
import { useTermsQuery } from "@/hooks/use-terms"
import type { CourseOut, DegreePlanOut, OptimizationMessageOut, PlanCourseOut, PlanCourseProgramOut, TermOut } from "@/lib/types"
import { downloadPlanPdf } from "@/lib/export-plan-pdf"
import { cn } from "@/lib/utils"

interface PlanBoardProps {
  plan: DegreePlanOut
  courseDetailsDisabled?: boolean
  onPlanUpdated: (updatedPlan: DegreePlanOut) => void
}

interface TermColumn {
  term: TermOut
  courses: PlanCourseOut[]
  totalCredits: number
}

interface AcademicYearGroup {
  startYear: number
  terms: TermColumn[]
  totalCredits: number
}

/** Render a vertically stacked academic-year schedule with simple and detail views. */
export function PlanBoard({ plan, courseDetailsDisabled = false, onPlanUpdated }: PlanBoardProps) {
  const [viewMode, setViewMode] = useState<PlanViewMode>("simple")
  const [pdfExporting, setPdfExporting] = useState(false)
  const boardRef = useRef<HTMLDivElement>(null)
  const termsQuery = useTermsQuery()
  const swapOptionsQuery = usePlanSwapOptionsQuery(plan.degree_plan_id)
  if (termsQuery.isPending) return <LoadingState label="Loading terms…" />
  if (termsQuery.isError) return <ErrorState message="Couldn't load terms from the server." />
  if (plan.status === "INFEASIBLE" || plan.courses.length === 0) return <EmptyPlan plan={plan} />
  const termsById = new Map(termsQuery.data.map((term) => [term.term_id, term]))
  const academicYears = groupTermsByAcademicYear(groupCoursesByTerm(plan.courses, termsById))
  const swapOptionsByPlanCourseId: Record<number, CourseOut[]> = swapOptionsQuery.data ?? {}
  const existingCourseIds = new Set(plan.courses.map((planCourse) => planCourse.course.course_id))
  const termLoadWarnings = plan.messages.filter((message) => message.message_code?.startsWith("TERM_CREDIT_"))
  /** Capture the visible plan board and download it as a paginated PDF. */
  async function handleDownloadPdf(): Promise<void> {
    if (!boardRef.current || pdfExporting) return
    setPdfExporting(true)
    try {
      await downloadPlanPdf(boardRef.current, `${plan.plan_name ?? "recommended"}-degree-plan.pdf`)
      toast.success("Schedule PDF downloaded")
    } catch (error) {
      toast.error("Couldn't create the schedule PDF", { description: error instanceof Error ? error.message : undefined })
    } finally {
      setPdfExporting(false)
    }
  }
  return (
    <div ref={boardRef} className="space-y-5">
      <div data-pdf-section><PlanSummaryCard plan={plan} /></div>
      <BoardToolbar plan={plan} viewMode={viewMode} pdfExporting={pdfExporting} onViewModeChange={setViewMode} onDownloadPdf={handleDownloadPdf} />
      <div className="space-y-5">
        {academicYears.map((academicYear) => (
          <AcademicYearSection
            key={academicYear.startYear}
            academicYear={academicYear}
            degreePlanId={plan.degree_plan_id}
            planCourses={plan.courses}
            viewMode={viewMode}
            swapOptionsByPlanCourseId={swapOptionsByPlanCourseId}
            swapOptionsLoading={swapOptionsQuery.isPending || swapOptionsQuery.isFetching}
            existingCourseIds={existingCourseIds}
            termLoadWarnings={termLoadWarnings}
            courseDetailsDisabled={courseDetailsDisabled}
            onPlanUpdated={onPlanUpdated}
          />
        ))}
      </div>
    </div>
  )
}

/** Show the summary and infeasible empty state without schedule controls. */
function EmptyPlan({ plan }: { plan: DegreePlanOut }) {
  return (
    <div className="space-y-6">
      <PlanSummaryCard plan={plan} />
      <EmptyState icon={CalendarX} title="No schedule to show" description="This scenario couldn't be scheduled — see the messages above, adjust the constraints, and try again." />
    </div>
  )
}

/** Combine the view switch and an ownership legend into one compact control surface. */
function BoardToolbar({ plan, viewMode, pdfExporting, onViewModeChange, onDownloadPdf }: { plan: DegreePlanOut; viewMode: PlanViewMode; pdfExporting: boolean; onViewModeChange: (mode: PlanViewMode) => void; onDownloadPdf: () => void }) {
  return (
    <section className="rounded-xl border border-primary/15 bg-gradient-to-r from-primary/7 via-background to-gold/10 p-3 shadow-sm" data-pdf-section>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground"><Palette className="size-4" aria-hidden="true" /></span>
          <div><h2 className="text-sm font-semibold">Schedule key</h2><p className="text-xs text-muted-foreground">Colors and icons show course ownership.</p></div>
        </div>
        <div className="flex flex-wrap items-center gap-2" data-pdf-hide>
          <Button type="button" size="sm" variant="outline" disabled={pdfExporting} onClick={onDownloadPdf}>
            {pdfExporting ? <LoaderCircle className="size-4 animate-spin" /> : <Download className="size-4" />}
            {pdfExporting ? "Preparing PDF…" : "Download PDF"}
          </Button>
          <ViewModeSwitch viewMode={viewMode} onChange={onViewModeChange} />
        </div>
      </div>
      <CourseOwnershipLegend courses={plan.courses} detailed={viewMode === "detail"} />
    </section>
  )
}

/** Let the student switch between an icon-first overview and explanatory cards. */
function ViewModeSwitch({ viewMode, onChange }: { viewMode: PlanViewMode; onChange: (mode: PlanViewMode) => void }) {
  return (
    <div className="inline-flex rounded-lg border bg-background/70 p-1" role="group" aria-label="Schedule view">
      <Button type="button" size="sm" variant={viewMode === "simple" ? "default" : "ghost"} aria-pressed={viewMode === "simple"} onClick={() => onChange("simple")}><LayoutGrid className="size-4" />Simple</Button>
      <Button type="button" size="sm" variant={viewMode === "detail" ? "default" : "ghost"} aria-pressed={viewMode === "detail"} onClick={() => onChange("detail")}><ListTree className="size-4" />Details</Button>
    </div>
  )
}

/** Explain only the programs and fallback categories that occur in this plan. */
function CourseOwnershipLegend({ courses, detailed }: { courses: PlanCourseOut[]; detailed: boolean }) {
  const programs = uniquePrograms(courses)
  const roles = new Set(courses.map((course) => course.academic_role))
  return (
    <div className="mt-3 flex flex-wrap gap-1.5">
      {programs.map((program) => <LegendProgram key={`${program.program_code}-${program.program_role}`} program={program} detailed={detailed} />)}
      {roles.has("SHARED") ? <LegendChip icon={UsersRound} label="Shared" className="border-emerald-200 bg-emerald-50 text-emerald-800" /> : null}
      {roles.has("PROGRAM_ELECTIVE") ? <LegendChip icon={Shuffle} label={detailed ? "Program elective choice" : "Elective choice"} className="border-amber-200 bg-amber-50 text-amber-800" /> : null}
      {roles.has("CREDIT_FLOOR") ? <LegendChip icon={Target} label="Open degree credits" className="border-cyan-200 bg-cyan-50 text-cyan-800" /> : null}
      {roles.has("EXPLORATORY") ? <LegendChip icon={Compass} label="Exploratory" className="border-slate-300 bg-slate-100 text-slate-700" /> : null}
    </div>
  )
}

/** Render one actual selected program in the schedule legend. */
function LegendProgram({ program, detailed }: { program: PlanCourseProgramOut; detailed: boolean }) {
  const visual = programVisual(program.program_role)
  const shortCode = program.program_code.split("_")[0]
  const label = detailed ? `${shortCode} · ${programRoleLabel(program.program_role)}` : shortCode
  return <LegendChip icon={visual.icon} label={label} title={program.program_name} className={visual.className} />
}

/** Render one icon-led legend chip. */
function LegendChip({ icon: Icon, label, title = label, className }: { icon: LucideIcon; label: string; title?: string; className: string }) {
  return <span title={title} className={cn("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[0.7rem] font-semibold", className)}><Icon className="size-3.5" aria-hidden="true" />{label}</span>
}

/** Render one academic year with Fall, Spring, and optional Summer side by side. */
function AcademicYearSection(props: { academicYear: AcademicYearGroup; degreePlanId: number; planCourses: PlanCourseOut[]; viewMode: PlanViewMode; swapOptionsByPlanCourseId: Record<number, CourseOut[]>; swapOptionsLoading: boolean; existingCourseIds: Set<number>; termLoadWarnings: OptimizationMessageOut[]; courseDetailsDisabled: boolean; onPlanUpdated: (plan: DegreePlanOut) => void }) {
  const { academicYear } = props
  return (
    <section className="glass-panel rounded-2xl p-3 sm:p-4" data-pdf-section>
      <header className="mb-3 flex items-center justify-between gap-3 border-b pb-3">
        <div className="flex items-center gap-2"><span className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary"><CalendarRange className="size-4" /></span><div><h2 className="font-semibold">Academic year {academicYearLabel(academicYear.startYear)}</h2><p className="text-xs text-muted-foreground">{academicYear.terms.length} terms</p></div></div>
        <span className="font-mono text-xs font-semibold text-muted-foreground">{academicYear.totalCredits} cr</span>
      </header>
      <div className={cn("grid grid-cols-1 gap-3 md:grid-cols-2", academicYear.terms.length === 3 && "xl:grid-cols-3")}>
        {academicYear.terms.map((column) => <TermPanel key={column.term.term_id} column={column} {...props} />)}
      </div>
    </section>
  )
}

/** Render one term column inside its academic-year row. */
function TermPanel(props: { column: TermColumn; degreePlanId: number; planCourses: PlanCourseOut[]; viewMode: PlanViewMode; swapOptionsByPlanCourseId: Record<number, CourseOut[]>; swapOptionsLoading: boolean; existingCourseIds: Set<number>; termLoadWarnings: OptimizationMessageOut[]; courseDetailsDisabled: boolean; onPlanUpdated: (plan: DegreePlanOut) => void }) {
  const { column, degreePlanId, planCourses, viewMode, swapOptionsByPlanCourseId, swapOptionsLoading, existingCourseIds, termLoadWarnings, courseDetailsDisabled, onPlanUpdated } = props
  const warning = termLoadWarnings.find((message) => message.message_text.startsWith(column.term.term_code))
  const isOverloaded = warning?.message_code === "TERM_CREDIT_ABOVE_MAXIMUM"
  const TermIcon = termIcon(column.term.term_type)
  return (
    <div className={cn("flex min-w-0 flex-col gap-2.5 rounded-xl border bg-background/45 p-3", warning && "border-amber-300 ring-2 ring-amber-200/70")}>
      <div className="flex items-center justify-between gap-2 border-b pb-2"><div className="flex items-center gap-2"><TermIcon className="size-4 text-primary" /><h3 className="text-sm font-semibold">{termLabel(column.term)}</h3></div><span className={cn("font-mono text-xs text-muted-foreground", warning && "font-semibold text-amber-700")}>{column.totalCredits} cr</span></div>
      {warning ? <TermLoadNotice warning={warning} compact={viewMode === "simple"} /> : null}
      <div className="space-y-2">
        {column.courses.map((planCourse) => <PlanCourseCard key={planCourse.plan_course_id} degreePlanId={degreePlanId} planCourse={planCourse} planCourses={planCourses} viewMode={viewMode} moveNeedsAttention={isOverloaded} swapAlternatives={swapOptionsByPlanCourseId[planCourse.plan_course_id] ?? []} swapOptionsLoading={swapOptionsLoading} courseDetailsDisabled={courseDetailsDisabled} onSwapped={onPlanUpdated} />)}
      </div>
      <div data-pdf-hide><AddCourseButton degreePlanId={degreePlanId} termId={column.term.term_id} termLabel={column.term.term_code} existingCourseIds={existingCourseIds} needsAttention={warning?.message_code === "TERM_CREDIT_BELOW_MINIMUM"} onAdded={onPlanUpdated} /></div>
    </div>
  )
}

/** Explain one term-load problem, reducing prose in simple view. */
function TermLoadNotice({ warning, compact }: { warning: OptimizationMessageOut; compact: boolean }) {
  const isUnderloaded = warning.message_code === "TERM_CREDIT_BELOW_MINIMUM"
  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 p-2.5 text-amber-950" role="alert">
      <div className="flex items-start gap-2"><TriangleAlert className="mt-0.5 size-4 shrink-0 text-amber-600" /><div><p className="text-xs font-semibold">{isUnderloaded ? "Add credits" : "Reduce workload"}</p>{compact ? null : <p className="mt-1 text-[0.7rem] leading-relaxed text-amber-800">{warning.message_text}</p>}</div></div>
    </div>
  )
}

/** Bucket plan courses into chronological term columns. */
function groupCoursesByTerm(courses: PlanCourseOut[], termsById: Map<number, TermOut>): TermColumn[] {
  const columns = new Map<number, TermColumn>()
  for (const planCourse of courses) {
    const term = termsById.get(planCourse.term_id)
    if (!term) continue
    const column = columns.get(term.term_id) ?? { term, courses: [], totalCredits: 0 }
    column.courses.push(planCourse)
    column.totalCredits += planCourse.credit_hours
    columns.set(term.term_id, column)
  }
  return Array.from(columns.values()).sort((a, b) => a.term.sequence_index - b.term.sequence_index)
}

/** Group chronological term columns by Fall-start academic year. */
function groupTermsByAcademicYear(columns: TermColumn[]): AcademicYearGroup[] {
  const groups = new Map<number, AcademicYearGroup>()
  for (const column of columns) {
    const startYear = column.term.term_type === "FALL" ? column.term.academic_year : column.term.academic_year - 1
    const group = groups.get(startYear) ?? { startYear, terms: [], totalCredits: 0 }
    group.terms.push(column)
    group.totalCredits += column.totalCredits
    groups.set(startYear, group)
  }
  return Array.from(groups.values()).sort((a, b) => a.startYear - b.startYear)
}

/** Return unique program descriptors represented across the plan's course cards. */
function uniquePrograms(courses: PlanCourseOut[]): PlanCourseProgramOut[] {
  const programs = new Map<string, PlanCourseProgramOut>()
  for (const course of courses) for (const program of course.programs ?? []) programs.set(`${program.program_code}-${program.program_role}`, program)
  return Array.from(programs.values()).sort((a, b) => programRoleRank(a.program_role) - programRoleRank(b.program_role) || a.program_code.localeCompare(b.program_code))
}

/** Return icon and color styling for a scenario program role. */
function programVisual(role: string): { icon: LucideIcon; className: string } {
  if (role === "PRIMARY_MAJOR") return { icon: GraduationCap, className: "border-blue-200 bg-blue-50 text-blue-800" }
  if (role === "SECOND_MAJOR") return { icon: BadgePlus, className: "border-violet-200 bg-violet-50 text-violet-800" }
  if (role === "MINOR") return { icon: BookMarked, className: "border-rose-200 bg-rose-50 text-rose-800" }
  return { icon: Layers3, className: "border-cyan-200 bg-cyan-50 text-cyan-800" }
}

/** Return a readable label for one scenario program role. */
function programRoleLabel(role: string): string {
  return ({ PRIMARY_MAJOR: "Primary major", SECOND_MAJOR: "Second major", MINOR: "Minor", EMPHASIS: "Emphasis" } as Record<string, string>)[role] ?? "Program"
}

/** Sort primary, second-major, minor, and emphasis program markers consistently. */
function programRoleRank(role: string): number {
  return ({ PRIMARY_MAJOR: 0, SECOND_MAJOR: 1, MINOR: 2, EMPHASIS: 3 } as Record<string, number>)[role] ?? 4
}

/** Return a short Fall-start academic-year label. */
function academicYearLabel(startYear: number): string {
  return `${startYear}–${String(startYear + 1).slice(-2)}`
}

/** Return a human-readable term label without relying on compact catalog codes. */
function termLabel(term: TermOut): string {
  return `${term.term_type[0]}${term.term_type.slice(1).toLowerCase()} ${term.academic_year}`
}

/** Return the seasonal icon used for a term header. */
function termIcon(termType: string): LucideIcon {
  if (termType === "FALL") return Leaf
  if (termType === "SPRING") return Sprout
  return Sun
}
