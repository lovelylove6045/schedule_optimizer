import { useQuery } from "@tanstack/react-query"
import { searchCourses } from "@/lib/api/courses"

const MIN_SEARCH_LENGTH = 2

/** Search the catalog for courses matching `search`, skipped until the query
 * is long enough to avoid firing a request on every keystroke of "a". */
export function useCourseSearchQuery(search: string) {
  const trimmed = search.trim()
  return useQuery({
    queryKey: ["courses", "search", trimmed],
    queryFn: () => searchCourses(trimmed),
    enabled: trimmed.length >= MIN_SEARCH_LENGTH,
  })
}
