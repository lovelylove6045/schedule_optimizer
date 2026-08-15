import { Loader2, Trash2 } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { useRemovePlanCourseMutation } from "@/hooks/use-plan-mutations"
import type { DegreePlanOut, PlanCourseOut } from "@/lib/types"

interface RemoveCourseButtonProps {
  degreePlanId: number
  planCourse: PlanCourseOut
  onRemoved: (updatedPlan: DegreePlanOut) => void
}

/** Small "remove" affordance on a plan-board course tile: lets a student
 * delete a course from the plan entirely -- solver-assigned or student-added
 * -- without re-running the optimizer. */
export function RemoveCourseButton({ degreePlanId, planCourse, onRemoved }: RemoveCourseButtonProps) {
  const remove = useRemovePlanCourseMutation()
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon-xs"
      aria-label={`Remove ${planCourse.course.subject_code} ${planCourse.course.course_number} from this plan`}
      disabled={remove.isPending}
      className="shrink-0 text-muted-foreground hover:text-destructive"
      onClick={() => void performRemove(degreePlanId, planCourse, remove.mutateAsync, onRemoved)}
    >
      {remove.isPending ? (
        <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
      ) : (
        <Trash2 className="size-3.5" aria-hidden="true" />
      )}
    </Button>
  )
}

type RemoveMutationFn = (args: { degreePlanId: number; planCourseId: number }) => Promise<DegreePlanOut>

/** Run the remove-course mutation for one tile, reporting the outcome as a
 * toast and forwarding the updated plan on success. */
async function performRemove(
  degreePlanId: number,
  planCourse: PlanCourseOut,
  mutate: RemoveMutationFn,
  onRemoved: (updatedPlan: DegreePlanOut) => void,
): Promise<void> {
  try {
    const updatedPlan = await mutate({ degreePlanId, planCourseId: planCourse.plan_course_id })
    onRemoved(updatedPlan)
    toast.success(`Removed ${planCourse.course.subject_code} ${planCourse.course.course_number}`, {
      description: "You can add it back anytime from this term.",
    })
  } catch (error) {
    toast.error("Couldn't remove that course", { description: error instanceof Error ? error.message : undefined })
  }
}
