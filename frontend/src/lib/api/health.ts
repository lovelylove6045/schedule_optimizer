import { apiFetch } from "@/lib/api/client"

export interface HealthResponse {
  status: string
}

/** Check whether the backend API is reachable and responding. */
export function getHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/health")
}
