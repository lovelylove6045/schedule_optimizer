import { useQuery } from "@tanstack/react-query"
import { getProgramOverlapSuggestions, getProgramRequirements, listPrograms } from "@/lib/api/programs"
import type { ProgramType } from "@/lib/types"

/** Fetch every academic program in the catalog, cached for the whole session
 * (the catalog doesn't change while a user is planning). */
export function useProgramsQuery() {
  return useQuery({
    queryKey: ["programs"],
    queryFn: listPrograms,
    staleTime: Infinity,
  })
}

/** Fetch one program's flattened requirement sets, for the catalog browser's
 * program detail panel -- disabled until a program is actually selected. */
export function useProgramRequirementsQuery(programId: number | null) {
  return useQuery({
    queryKey: ["programs", programId, "requirements"],
    queryFn: () => getProgramRequirements(programId as number),
    enabled: programId !== null,
    staleTime: Infinity,
  })
}

/** Fetch programs that overlap well with `primaryProgramId` -- e.g. minors that
 * mostly reuse the primary major's courses -- skipped until a primary program
 * is chosen. Narrow to `programType` to match the role currently being added. */
export function useProgramOverlapSuggestionsQuery(primaryProgramId: number | null, programType?: ProgramType) {
  return useQuery({
    queryKey: ["programs", primaryProgramId, "overlap-suggestions", programType],
    queryFn: () => getProgramOverlapSuggestions(primaryProgramId as number, programType),
    enabled: primaryProgramId !== null,
    staleTime: Infinity,
  })
}
