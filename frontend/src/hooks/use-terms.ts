import { useQuery } from "@tanstack/react-query"
import { listTerms } from "@/lib/api/terms"

/** Fetch every term in chronological order, cached for the whole session. */
export function useTermsQuery() {
  return useQuery({
    queryKey: ["terms"],
    queryFn: listTerms,
    staleTime: Infinity,
  })
}
