import { useQuery } from "@tanstack/react-query"
import { listColleges } from "@/lib/api/colleges"

/** Fetch every college/school, cached for the whole session (the catalog's
 * organizational hierarchy doesn't change while a user is planning). */
export function useCollegesQuery() {
  return useQuery({
    queryKey: ["colleges"],
    queryFn: listColleges,
    staleTime: Infinity,
  })
}
