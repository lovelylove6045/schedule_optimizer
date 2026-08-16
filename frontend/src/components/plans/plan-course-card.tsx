import { RemoveCourseButton } from "@/components/plans/remove-course-button"
import { SwapCourseButton } from "@/components/plans/swap-course-button"
import { MoveCourseButton } from "@/components/plans/move-course-button"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type { CourseOut, DegreePlanOut, PlanCourseOut } from "@/lib/types"

interface PlanCourseCardProps {
  degreePlanId: number
  planCourse: PlanCourseOut
  swapAlternatives: CourseOut[]
  onSwapped: (updatedPlan: DegreePlanOut) => void
  onRemoved: (updatedPlan: DegreePlanOut) => void
}

/** Show one explained, role-coded course with only its valid edit affordances. */
export function PlanCourseCard({ degreePlanId, planCourse, swapAlternatives, onSwapped, onRemoved }: PlanCourseCardProps) {
  const { course } = planCourse
  return (
    <div className={cn("glass-raised glass-interactive rounded-lg border-l-4 p-3", roleBorder(planCourse.academic_role))}>
      <div className="flex items-start justify-between gap-2">
        <p className="font-mono text-xs font-semibold text-primary">
          {course.subject_code} {course.course_number}
        </p>
        <div className="flex shrink-0 items-center gap-1">
          <p className="font-mono text-xs text-muted-foreground">{planCourse.credit_hours} cr</p>
          <SwapCourseButton
            degreePlanId={degreePlanId}
            planCourse={planCourse}
            alternatives={swapAlternatives}
            onSwapped={onSwapped}
          />
          <MoveCourseButton degreePlanId={degreePlanId} planCourse={planCourse} onMoved={onSwapped} />
          <RemoveCourseButton degreePlanId={degreePlanId} planCourse={planCourse} onRemoved={onRemoved} />
        </div>
      </div>
      <p className="mt-1 text-sm leading-snug">{course.course_title}</p>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <Badge variant="outline" className="text-[0.65rem]">{roleLabel(planCourse.academic_role)}</Badge>
        {!planCourse.is_removable ? <Badge variant="secondary" className="text-[0.65rem]">Locked</Badge> : null}
      </div>
      <p className="mt-2 text-xs text-muted-foreground">{planCourse.selection_reasons.join(" · ")}</p>
    </div>
  )
}

/** Map backend academic roles to accessible left-border categories. */
function roleBorder(role: string): string {
  if (role === "SHARED") return "border-l-emerald-500"
  if (role === "ADDITIONAL_PROGRAM") return "border-l-violet-500"
  if (role === "PRIMARY_REQUIRED") return "border-l-blue-500"
  if (role === "EXPLORATORY") return "border-l-slate-400"
  return "border-l-amber-500"
}

/** Return a short visible label so categories never rely on color alone. */
function roleLabel(role: string): string {
  return ({
    SHARED: "Shared requirement",
    ADDITIONAL_PROGRAM: "Additional program",
    PRIMARY_REQUIRED: "Primary requirement",
    EXPLORATORY: "Exploratory",
    CREDIT_FLOOR: "Degree-credit elective",
  } as Record<string, string>)[role] ?? "Degree course"
}
