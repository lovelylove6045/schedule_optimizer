import { apiFetch } from "@/lib/api/client"
import type { TermOut } from "@/lib/types"

/** Fetch every term in chronological order. */
export function listTerms(): Promise<TermOut[]> {
  return apiFetch<TermOut[]>("/terms")
}
