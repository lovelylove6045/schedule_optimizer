import {
  BadgePlus,
  BookMarked,
  Compass,
  GraduationCap,
  GitBranch,
  Layers3,
  LockKeyhole,
  Shuffle,
  Target,
  UsersRound,
  type LucideIcon,
} from "lucide-react"
import { Link } from "react-router-dom"
import { MoveCourseButton } from "@/components/plans/move-course-button"
import { SwapCourseButton } from "@/components/plans/swap-course-button"
import { Badge } from "@/components/ui/badge"
import type { CourseOut, DegreePlanOut, PlanCourseOut, PlanCourseProgramOut } from "@/lib/types"
import { cn } from "@/lib/utils"

export type PlanViewMode = "simple" | "detail"

interface PlanCourseCardProps {
  degreePlanId: number
  planCourse: PlanCourseOut
  planCourses: PlanCourseOut[]
  viewMode: PlanViewMode
  moveNeedsAttention?: boolean
  swapAlternatives: CourseOut[]
  swapOptionsLoading?: boolean
  courseDetailsDisabled?: boolean
  onSwapped: (updatedPlan: DegreePlanOut) => void
}

/** Show one role-coded course with compact or explanatory content. */
export function PlanCourseCard(props: PlanCourseCardProps) {
  const { planCourse, viewMode } = props
  const { course } = planCourse
  return (
    <article className={cn("glass-raised glass-interactive rounded-lg border-l-4", viewMode === "simple" ? "p-2.5" : "p-3", courseBorder(planCourse))}>
      <div className="flex items-start justify-between gap-2">
        <p className="min-w-0 truncate text-xs leading-5" title={`${course.subject_code} ${course.course_number} (${course.course_title})`}>
          <span className="font-mono font-bold text-primary">{course.subject_code} {course.course_number}</span>
          {viewMode === "simple" ? <span className="ml-1 text-foreground">({course.course_title})</span> : null}
        </p>
        <div className="flex shrink-0 items-center gap-0.5">
          <span className="mr-0.5 font-mono text-[0.68rem] text-muted-foreground">{planCourse.credit_hours} cr</span>
          <CourseActions {...props} />
        </div>
      </div>
      {viewMode === "detail" ? <p className="mt-1 text-sm leading-snug">{course.course_title}</p> : null}
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <ProgramMarkers planCourse={planCourse} detailed={viewMode === "detail"} />
        {viewMode === "detail" ? <Badge variant="outline" className="text-[0.65rem]">{roleLabel(planCourse.academic_role)}</Badge> : null}
      </div>
      {viewMode === "detail" ? <p className="mt-2 text-xs text-muted-foreground">{planCourse.selection_reasons.join(" · ")}</p> : null}
    </article>
  )
}

/** Render swap, move, and lock affordances without adding explanatory card text. */
function CourseActions(props: PlanCourseCardProps) {
  const { degreePlanId, planCourse, planCourses, moveNeedsAttention, swapAlternatives, swapOptionsLoading, courseDetailsDisabled, onSwapped } = props
  return (
    <span className="flex items-center gap-0.5" data-pdf-hide>
      {courseDetailsDisabled ? (
        <span title="Course rules unlock when comparison plans finish" aria-label="Course rules unavailable while comparison plans are generating" aria-disabled="true" className="inline-flex size-6 shrink-0 cursor-not-allowed items-center justify-center rounded-md text-muted-foreground/40">
          <GitBranch className="size-3.5" aria-hidden="true" />
        </span>
      ) : (
        <Link to="/courses" state={{ course: planCourse.course }} title="View prerequisites" aria-label={`View prerequisites for ${planCourse.course.subject_code} ${planCourse.course.course_number}`} className="inline-flex size-6 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground">
          <GitBranch className="size-3.5" aria-hidden="true" />
        </Link>
      )}
      <SwapCourseButton degreePlanId={degreePlanId} planCourse={planCourse} alternatives={swapAlternatives} loading={swapOptionsLoading} onSwapped={onSwapped} />
      <MoveCourseButton degreePlanId={degreePlanId} planCourse={planCourse} planCourses={planCourses} needsAttention={moveNeedsAttention} onMoved={onSwapped} />
      {!planCourse.is_removable ? (
        <span title="Required course — cannot be removed" aria-label="Required course — cannot be removed" className="inline-flex size-6 shrink-0 items-center justify-center rounded-md text-muted-foreground">
          <LockKeyhole className="size-3.5" aria-hidden="true" />
        </span>
      ) : null}
    </span>
  )
}

/** Identify every program using a course with compact icons and optional labels. */
function ProgramMarkers({ planCourse, detailed }: { planCourse: PlanCourseOut; detailed: boolean }) {
  const programs = planCourse.programs ?? []
  if (programs.length === 0) return <FallbackRoleMarker role={planCourse.academic_role} detailed={detailed} />
  return (
    <>
      {planCourse.academic_role === "SHARED" ? <IconMarker icon={UsersRound} label="Shared" className="border-emerald-200 bg-emerald-50 text-emerald-800" detailed={detailed} /> : null}
      {planCourse.academic_role === "PROGRAM_ELECTIVE" ? <IconMarker icon={Shuffle} label="Elective choice" className="border-amber-200 bg-amber-50 text-amber-800" detailed={detailed} /> : null}
      {programs.map((program) => <ProgramMarker key={`${program.program_code}-${program.program_role}`} program={program} detailed={detailed} />)}
    </>
  )
}

/** Render one program-specific marker using its scenario role. */
function ProgramMarker({ program, detailed }: { program: PlanCourseProgramOut; detailed: boolean }) {
  const visual = programVisual(program.program_role)
  const shortCode = program.program_code.split("_")[0]
  const label = detailed ? `${shortCode} · ${programRoleLabel(program.program_role)}` : shortCode
  return <IconMarker icon={visual.icon} label={label} title={`${program.program_name} — ${programRoleLabel(program.program_role)}`} className={visual.className} detailed={true} />
}

/** Render a semantic icon chip, showing text only when requested by its caller. */
function IconMarker({ icon: Icon, label, title = label, className, detailed }: { icon: LucideIcon; label: string; title?: string; className: string; detailed: boolean }) {
  return (
    <span title={title} aria-label={title} className={cn("inline-flex h-6 items-center justify-center gap-1 rounded-full border px-1.5 text-[0.65rem] font-semibold", className)}>
      <Icon className="size-3" aria-hidden="true" />
      {detailed ? <span>{label}</span> : null}
    </span>
  )
}

/** Show a semantic marker for courses not owned by a particular program. */
function FallbackRoleMarker({ role, detailed }: { role: string; detailed: boolean }) {
  if (role === "EXPLORATORY") return <IconMarker icon={Compass} label="Exploratory" className="border-slate-300 bg-slate-100 text-slate-700" detailed={detailed} />
  return <IconMarker icon={Target} label="Open degree credits" className="border-cyan-200 bg-cyan-50 text-cyan-800" detailed={detailed} />
}

/** Return the card edge color for actual program ownership or fallback role. */
function courseBorder(planCourse: PlanCourseOut): string {
  if (planCourse.academic_role === "SHARED") return "border-l-emerald-500"
  if (planCourse.academic_role === "PROGRAM_ELECTIVE") return "border-l-amber-500"
  if (planCourse.academic_role === "CREDIT_FLOOR") return "border-l-cyan-500"
  const role = planCourse.programs?.[0]?.program_role
  if (role === "PRIMARY_MAJOR") return "border-l-blue-500"
  if (role === "SECOND_MAJOR") return "border-l-violet-500"
  if (role === "MINOR") return "border-l-rose-500"
  if (role === "EMPHASIS") return "border-l-cyan-500"
  if (planCourse.academic_role === "EXPLORATORY") return "border-l-slate-400"
  return "border-l-cyan-500"
}

/** Return icon and color styling for one scenario program role. */
function programVisual(role: string): { icon: LucideIcon; className: string } {
  if (role === "PRIMARY_MAJOR") return { icon: GraduationCap, className: "border-blue-200 bg-blue-50 text-blue-800" }
  if (role === "SECOND_MAJOR") return { icon: BadgePlus, className: "border-violet-200 bg-violet-50 text-violet-800" }
  if (role === "MINOR") return { icon: BookMarked, className: "border-rose-200 bg-rose-50 text-rose-800" }
  return { icon: Layers3, className: "border-cyan-200 bg-cyan-50 text-cyan-800" }
}

/** Return a readable program-role label for the detail view and tooltips. */
function programRoleLabel(role: string): string {
  return ({ PRIMARY_MAJOR: "Primary major", SECOND_MAJOR: "Second major", MINOR: "Minor", EMPHASIS: "Emphasis" } as Record<string, string>)[role] ?? "Program"
}

/** Return the broad academic-purpose label retained in the detail view. */
function roleLabel(role: string): string {
  return ({ SHARED: "Shared requirement", ADDITIONAL_PROGRAM: "Additional program", PRIMARY_REQUIRED: "Primary requirement", PROGRAM_ELECTIVE: "Program elective choice", EXPLORATORY: "Exploratory", CREDIT_FLOOR: "Open degree credits" } as Record<string, string>)[role] ?? "Degree course"
}
