import { BookOpen, X } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { EmptyState } from "@/components/shared/empty-state"
import { CourseSearchCombobox } from "@/components/wizard/course-search-combobox"
import { TransferCreditForm } from "@/components/wizard/transfer-credit-form"
import { useScenarioBuilder } from "@/state/scenario-builder-context"
import type { CourseOut, StudentCreditIn } from "@/lib/types"

/** Screen 2: coursework already completed (or in progress), plus transfer credit. */
export function StepAcademicProgress() {
  const { draft, dispatch } = useScenarioBuilder()
  const institutionalCourseIds = new Set(
    draft.completedCourses.filter((c) => c.course_id != null).map((c) => c.course_id as number),
  )
  return (
    <Card>
      <CardHeader>
        <CardTitle>What have you already completed?</CardTitle>
        <CardDescription>
          Add courses you've finished (or transfer credit) so the plan doesn't repeat them.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <CourseSearchCombobox
          excludeCourseIds={institutionalCourseIds}
          onSelect={(course) =>
            dispatch({
              type: "ADD_COMPLETED_COURSE",
              credit: { course_id: course.course_id, source_type: "INSTITUTIONAL", status: "COMPLETED", grade: "A" },
              courseDetail: course,
            })
          }
        />
        <TransferCreditForm onAdd={(credit) => dispatch({ type: "ADD_COMPLETED_COURSE", credit })} />
        {draft.completedCourses.length === 0 ? (
          <EmptyState
            icon={BookOpen}
            title="No completed coursework added yet"
            description="That's fine if you're a first-year student -- otherwise, search above to add courses."
          />
        ) : (
          <ul className="divide-y rounded-lg border">
            {draft.completedCourses.map((credit, index) => (
              <CompletedCourseRow
                key={index}
                credit={credit}
                courseDetail={credit.course_id != null ? draft.courseDetailsById[credit.course_id] : undefined}
                onRemove={() => dispatch({ type: "REMOVE_COMPLETED_COURSE", index })}
              />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

interface CompletedCourseRowProps {
  credit: StudentCreditIn
  courseDetail: CourseOut | undefined
  onRemove: () => void
}

/** One row in the completed-coursework list: title, credit hours/grade, and a remove button. */
function CompletedCourseRow({ credit, courseDetail, onRemove }: CompletedCourseRowProps) {
  const title = courseDetail
    ? `${courseDetail.subject_code} ${courseDetail.course_number} — ${courseDetail.course_title}`
    : credit.external_course_title
  const subtitle = courseDetail
    ? `${courseDetail.credit_hours} credit hours`
    : `Transfer credit · ${credit.credits_earned ?? 0} credit hours`
  return (
    <li className="flex items-center justify-between gap-3 px-4 py-3">
      <div className="min-w-0">
        <p className="truncate text-sm font-medium">{title}</p>
        <p className="text-xs text-muted-foreground">{subtitle}</p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {credit.grade ? (
          <Badge variant="secondary" className="font-mono">
            {credit.grade}
          </Badge>
        ) : null}
        <Button variant="ghost" size="icon-sm" onClick={onRemove} aria-label="Remove">
          <X className="size-4" />
        </Button>
      </div>
    </li>
  )
}
