import { useState } from "react"
import { Loader2, Plus } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { useCourseSearchQuery } from "@/hooks/use-course-search"
import { useAddPlanCourseMutation } from "@/hooks/use-plan-mutations"
import type { CourseOut, DegreePlanOut } from "@/lib/types"

interface AddCourseButtonProps {
  degreePlanId: number
  termId: number
  termLabel: string
  existingCourseIds: Set<number>
  onAdded: (updatedPlan: DegreePlanOut) => void
}

/** "+ Add course" affordance at the bottom of a plan-board term column: lets a
 * student place a brand-new course into that exact term -- an extra elective
 * beyond what the solver assigned -- without re-running the optimizer.
 * Subject to the same offering/credit-cap/prerequisite checks as a swap. */
export function AddCourseButton({ degreePlanId, termId, termLabel, existingCourseIds, onAdded }: AddCourseButtonProps) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState("")
  const add = useAddPlanCourseMutation()
  const { data, isFetching, isError } = useCourseSearchQuery(search)
  const results = (data ?? []).filter((course) => !existingCourseIds.has(course.course_id))
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={add.isPending}
          className="w-full justify-start text-muted-foreground"
        >
          {add.isPending ? <Loader2 className="size-3.5 animate-spin" aria-hidden="true" /> : <Plus className="size-3.5" aria-hidden="true" />}
          Add course
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-72 p-0">
        <Command shouldFilter={false}>
          <CommandInput placeholder="Subject, number, or title…" value={search} onValueChange={setSearch} />
          <CommandList>
            <SearchResultsEmptyState search={search} isFetching={isFetching} isError={isError} />
            <CommandGroup heading={`Add to ${termLabel}`}>
              {results.map((course) => (
                <CommandItem
                  key={course.course_id}
                  value={`${course.subject_code} ${course.course_number} ${course.course_title}`}
                  onSelect={() => {
                    setOpen(false)
                    setSearch("")
                    void performAdd(degreePlanId, termId, course, add.mutateAsync, onAdded)
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

/** The right empty-state message for a course search's current phase (too
 * short, loading, errored, or genuinely no matches). */
function SearchResultsEmptyState({
  search,
  isFetching,
  isError,
}: {
  search: string
  isFetching: boolean
  isError: boolean
}) {
  if (search.trim().length < 2) return <CommandEmpty>Type at least 2 characters to search.</CommandEmpty>
  if (isFetching) return <CommandEmpty>Searching…</CommandEmpty>
  if (isError) return <CommandEmpty>Couldn't search courses. Try again.</CommandEmpty>
  return <CommandEmpty>No matching courses.</CommandEmpty>
}

type AddMutationFn = (args: { degreePlanId: number; courseId: number; termId: number }) => Promise<DegreePlanOut>

/** Run the add-course mutation for one selection, reporting the outcome as a
 * toast and forwarding the updated plan on success. */
async function performAdd(
  degreePlanId: number,
  termId: number,
  course: CourseOut,
  mutate: AddMutationFn,
  onAdded: (updatedPlan: DegreePlanOut) => void,
): Promise<void> {
  try {
    const updatedPlan = await mutate({ degreePlanId, courseId: course.course_id, termId })
    onAdded(updatedPlan)
    toast.success(`Added ${course.subject_code} ${course.course_number}`, { description: course.course_title })
  } catch (error) {
    toast.error("Couldn't add that course", { description: error instanceof Error ? error.message : undefined })
  }
}
