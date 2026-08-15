import { useQuery } from "@tanstack/react-query"
import { listPrograms } from "@/lib/api/programs"

/** Fetch every academic program in the catalog, cached for the whole session
 * (the catalog doesn't change while a user is planning). */
export function useProgramsQuery() {
  return useQuery({
    queryKey: ["programs"],
    queryFn: listPrograms,
    staleTime: Infinity,
  })
}
