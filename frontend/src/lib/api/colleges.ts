import { apiFetch } from "@/lib/api/client"
import type { CollegeOut } from "@/lib/types"

/** Fetch every college/school, for the wizard's "which school?" first step. */
export function listColleges(): Promise<CollegeOut[]> {
  return apiFetch<CollegeOut[]>("/colleges")
}
