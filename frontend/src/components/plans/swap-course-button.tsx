import { useState } from "react"
import { Loader2, Repeat } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { useSwapPlanCourseMutation } from "@/hooks/use-plan-mutations"
import type { CourseOut, DegreePlanOut, PlanCourseOut } from "@/lib/types"

interface SwapCourseButtonProps {
  degreePlanId: number
  planCourse: PlanCourseOut
  alternatives: CourseOut[]
  onSwapped: (updatedPlan: DegreePlanOut) => void
}

/** Small "swap" affordance on a plan-board course tile: lets a student replace
 * a flexible requirement's solver-picked course with another valid option for
 * that exact term slot -- Stellic/DegreeWorks style -- without re-running the
 * optimizer. Renders nothing for a course with no real alternative. */
export function SwapCourseButton({ degreePlanId, planCourse, alternatives, onSwapped }: SwapCourseButtonProps) {
  const [open, setOpen] = useState(false)
  const swap = useSwapPlanCourseMutation()
  const otherOptions = alternatives.filter((course) => course.course_id !== planCourse.course.course_id)
  if (otherOptions.length === 0) return null
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon-xs"
          aria-label={`Swap ${planCourse.course.subject_code} ${planCourse.course.course_number} for another course`}
          disabled={swap.isPending}
          className="shrink-0"
        >
          {swap.isPending ? <Loader2 className="size-3.5 animate-spin" aria-hidden="true" /> : <Repeat className="size-3.5" aria-hidden="true" />}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-72 p-0">
        <Command>
          <CommandInput placeholder="Swap for..." />
          <CommandList>
            <CommandEmpty>No other options for this requirement.</CommandEmpty>
            <CommandGroup heading="Alternatives for this requirement">
              {otherOptions.map((course) => (
                <CommandItem
                  key={course.course_id}
                  value={`${course.subject_code} ${course.course_number} ${course.course_title}`}
                  onSelect={() => {
                    setOpen(false)
                    void performSwap(degreePlanId, planCourse, course, swap.mutateAsync, onSwapped)
                  }}
                >
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className="font-mono text-xs font-semibold">
                      {course.subject_code} {course.course_number}
                    </span>
                    <span className="truncate text-xs text-muted-foreground">{course.course_title}</span>
                  </span>
                  <span className="shrink-0 font-mono text-[0.7rem] text-muted-foreground">
                    {course.credit_hours} cr
                  </span>
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}

type SwapMutationFn = (args: {
  degreePlanId: number
  planCourseId: number
  newCourseId: number
}) => Promise<DegreePlanOut>

/** Run the swap mutation for one course selection, reporting the outcome as a
 * toast and forwarding the updated plan on success. */
async function performSwap(
  degreePlanId: number,
  planCourse: PlanCourseOut,
  newCourse: CourseOut,
  mutate: SwapMutationFn,
  onSwapped: (updatedPlan: DegreePlanOut) => void,
): Promise<void> {
  try {
    const updatedPlan = await mutate({
      degreePlanId, planCourseId: planCourse.plan_course_id, newCourseId: newCourse.course_id,
    })
    onSwapped(updatedPlan)
    toast.success(`Swapped in ${newCourse.subject_code} ${newCourse.course_number}`, {
      description: `Replaced ${planCourse.course.subject_code} ${planCourse.course.course_number} for the same term.`,
    })
  } catch (error) {
    toast.error("Couldn't swap that course", {
      description: error instanceof Error ? error.message : undefined,
    })
  }
}
