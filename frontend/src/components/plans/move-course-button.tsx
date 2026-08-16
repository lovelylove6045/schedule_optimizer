import { useState } from "react"
import { CalendarArrowDown, Loader2 } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Command, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { useMovePlanCourseMutation } from "@/hooks/use-plan-mutations"
import { useTermsQuery } from "@/hooks/use-terms"
import type { DegreePlanOut, PlanCourseOut } from "@/lib/types"

/** Offer chronological target terms and let the backend validate a full-plan move. */
export function MoveCourseButton({
  degreePlanId,
  planCourse,
  onMoved,
}: {
  degreePlanId: number
  planCourse: PlanCourseOut
  onMoved: (plan: DegreePlanOut) => void
}) {
  const [open, setOpen] = useState(false)
  const terms = useTermsQuery()
  const move = useMovePlanCourseMutation()
  if (!planCourse.is_movable || !terms.data) return null
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon-xs" aria-label={`Move ${planCourse.course.subject_code} ${planCourse.course.course_number}`}>
          {move.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <CalendarArrowDown className="size-3.5" />}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-64 p-0">
        <Command>
          <CommandInput placeholder="Move to term…" />
          <CommandList>
            <CommandGroup heading="Available planning terms">
              {terms.data.filter((term) => term.term_id !== planCourse.term_id).map((term) => (
                <CommandItem key={term.term_id} value={term.term_code} onSelect={() => {
                  setOpen(false)
                  void move.mutateAsync({ degreePlanId, planCourseId: planCourse.plan_course_id, termId: term.term_id })
                    .then((plan) => {
                      onMoved(plan)
                      toast.success(`Moved to ${term.term_code}`)
                    })
                    .catch((error) => toast.error("That move would invalidate the plan", { description: error instanceof Error ? error.message : undefined }))
                }}>
                  {term.term_code}
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
