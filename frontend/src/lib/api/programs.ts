import { apiFetch } from "@/lib/api/client"
import type { ProgramOut, RequirementSetOut } from "@/lib/types"

/** Fetch every academic program in the catalog. */
export function listPrograms(): Promise<ProgramOut[]> {
  return apiFetch<ProgramOut[]>("/programs")
}

/** Fetch a program's flattened, unmatched requirement sets. */
export function getProgramRequirements(programId: number): Promise<RequirementSetOut[]> {
  return apiFetch<RequirementSetOut[]>(`/programs/${programId}/requirements`)
}
