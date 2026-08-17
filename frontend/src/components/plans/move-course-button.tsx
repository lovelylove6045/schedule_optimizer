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
  planCourses,
  needsAttention = false,
  onMoved,
}: {
  degreePlanId: number
  planCourse: PlanCourseOut
  planCourses: PlanCourseOut[]
  needsAttention?: boolean
  onMoved: (plan: DegreePlanOut) => void
}) {
  const [open, setOpen] = useState(false)
  const terms = useTermsQuery()
  const move = useMovePlanCourseMutation()
  if (!planCourse.is_movable || !terms.data) return null
  const creditsByTerm = planCourses.reduce<Record<number, number>>((totals, course) => {
    totals[course.term_id] = (totals[course.term_id] ?? 0) + course.credit_hours
    return totals
  }, {})
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant={needsAttention ? "outline" : "ghost"}
          size="icon-xs"
          aria-label={`Move ${planCourse.course.subject_code} ${planCourse.course.course_number}`}
          title={needsAttention ? "Move this course to reduce the term workload" : "Move course to another term"}
          className={needsAttention ? "border-amber-400 bg-amber-50 text-amber-800 hover:bg-amber-100" : undefined}
        >
          {move.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <CalendarArrowDown className="size-3.5" />}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-64 p-0">
        <Command>
          <CommandInput placeholder="Move to term…" />
          <CommandList>
            <p className="border-b px-3 py-2 text-[0.7rem] leading-relaxed text-muted-foreground">
              Offerings, prerequisites, and term loads are rechecked after every move.
            </p>
            <CommandGroup heading="Available planning terms">
              {terms.data.filter((term) => term.term_id !== planCourse.term_id).map((term) => (
                <CommandItem key={term.term_id} value={term.term_code} onSelect={() => {
                  setOpen(false)
                  void move.mutateAsync({ degreePlanId, planCourseId: planCourse.plan_course_id, termId: term.term_id })
                    .then((plan) => {
                      onMoved(plan)
                      const warnings = plan.messages.filter((message) => message.message_code?.startsWith("TERM_CREDIT_"))
                      if (warnings.length > 0) {
                        toast.warning(`Moved to ${term.term_code} — workload needs attention`, {
                          description: warnings.map((warning) => warning.message_text).join(" "),
                        })
                      } else {
                        toast.success(`Moved to ${term.term_code}`)
                      }
                    })
                    .catch((error) => toast.error("That move would invalidate the plan", { description: error instanceof Error ? error.message : undefined }))
                }}>
                  <span className="flex w-full items-center justify-between gap-3">
                    <span>{term.term_code}</span>
                    <span className="font-mono text-xs text-muted-foreground">
                      {creditsByTerm[term.term_id] ?? 0} → {(creditsByTerm[term.term_id] ?? 0) + planCourse.credit_hours} cr
                    </span>
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
