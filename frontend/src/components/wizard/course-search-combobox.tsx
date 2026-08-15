import { useState } from "react"
import { Search } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { useCourseSearchQuery } from "@/hooks/use-course-search"
import type { CourseOut } from "@/lib/types"

interface CourseSearchComboboxProps {
  onSelect: (course: CourseOut) => void
  excludeCourseIds?: Set<number>
}

/** Remote-searched course picker (Screen 2): types a subject/number/title,
 * gets live matches from GET /courses?search=. */
export function CourseSearchCombobox({ onSelect, excludeCourseIds }: CourseSearchComboboxProps) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState("")
  const { data, isFetching, isError } = useCourseSearchQuery(search)
  const results = (data ?? []).filter((course) => !excludeCourseIds?.has(course.course_id))
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" className="w-full justify-start font-normal text-muted-foreground">
          <Search className="size-4" />
          Search for a completed course (e.g. "CS 101" or "calculus")
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-(--radix-popover-trigger-width) p-0" align="start">
        <Command shouldFilter={false}>
          <CommandInput placeholder="Subject, number, or title…" value={search} onValueChange={setSearch} />
          <CommandList>
            {search.trim().length < 2 ? (
              <CommandEmpty>Type at least 2 characters to search.</CommandEmpty>
            ) : isFetching ? (
              <CommandEmpty>Searching…</CommandEmpty>
            ) : isError ? (
              <CommandEmpty>Couldn't search courses. Try again.</CommandEmpty>
            ) : (
              <CommandEmpty>No matching courses.</CommandEmpty>
            )}
            <CommandGroup>
              {results.map((course) => (
                <CommandItem
                  key={course.course_id}
                  value={String(course.course_id)}
                  onSelect={() => {
                    onSelect(course)
                    setSearch("")
                    setOpen(false)
                  }}
                >
                  <span className="flex flex-col">
                    <span className="font-mono text-xs">
                      {course.subject_code} {course.course_number}
                    </span>
                    <span>{course.course_title}</span>
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
