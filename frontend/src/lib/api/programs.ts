import { apiFetch } from "@/lib/api/client"
import type { ProgramOut, ProgramOverlapOut, ProgramType, RequirementSetOut } from "@/lib/types"

/** Fetch every academic program in the catalog. */
export function listPrograms(): Promise<ProgramOut[]> {
  return apiFetch<ProgramOut[]>("/programs")
}

/** Fetch a program's flattened, unmatched requirement sets. */
export function getProgramRequirements(programId: number): Promise<RequirementSetOut[]> {
  return apiFetch<RequirementSetOut[]>(`/programs/${programId}/requirements`)
}

/** Fetch other programs ranked by how much they'd reuse `programId`'s own
 * courses, optionally narrowed to one `programType` (e.g. only minors). */
export function getProgramOverlapSuggestions(
  programId: number,
  programType?: ProgramType,
): Promise<ProgramOverlapOut[]> {
  return apiFetch<ProgramOverlapOut[]>(`/programs/${programId}/overlap-suggestions`, {
    searchParams: { program_type: programType },
  })
}
