import { RemoveCourseButton } from "@/components/plans/remove-course-button"
import { SwapCourseButton } from "@/components/plans/swap-course-button"
import type { CourseOut, DegreePlanOut, PlanCourseOut } from "@/lib/types"

interface PlanCourseCardProps {
  degreePlanId: number
  planCourse: PlanCourseOut
  swapAlternatives: CourseOut[]
  onSwapped: (updatedPlan: DegreePlanOut) => void
  onRemoved: (updatedPlan: DegreePlanOut) => void
}

/** One course tile inside a semester column of the plan board (Screen 6), with
 * swap/remove affordances -- swap when this exact slot has a real
 * alternative course, remove always available. */
export function PlanCourseCard({ degreePlanId, planCourse, swapAlternatives, onSwapped, onRemoved }: PlanCourseCardProps) {
  const { course } = planCourse
  return (
    <div className="glass-raised glass-interactive rounded-lg p-3">
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
          <RemoveCourseButton degreePlanId={degreePlanId} planCourse={planCourse} onRemoved={onRemoved} />
        </div>
      </div>
      <p className="mt-1 text-sm leading-snug">{course.course_title}</p>
    </div>
  )
}
