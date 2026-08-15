import type { PlanCourseOut } from "@/lib/types"

interface PlanCourseCardProps {
  planCourse: PlanCourseOut
}

/** One course tile inside a semester column of the plan board (Screen 6). */
export function PlanCourseCard({ planCourse }: PlanCourseCardProps) {
  const { course } = planCourse
  return (
    <div className="rounded-lg border bg-card p-3 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <p className="font-mono text-xs font-semibold text-primary">
          {course.subject_code} {course.course_number}
        </p>
        <p className="shrink-0 font-mono text-xs text-muted-foreground">{planCourse.credit_hours} cr</p>
      </div>
      <p className="mt-1 text-sm leading-snug">{course.course_title}</p>
    </div>
  )
}
