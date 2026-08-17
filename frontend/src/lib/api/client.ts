export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"

/** Thrown for any non-2xx response, carrying the HTTP status for callers that need it. */
export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = "ApiError"
    this.status = status
  }
}

interface RequestOptions {
  method?: "GET" | "POST" | "DELETE"
  body?: unknown
  searchParams?: Record<string, string | number | undefined>
  signal?: AbortSignal
}

/** Fetch one JSON resource from the backend API, throwing ApiError on failure. */
export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const url = buildUrl(path, options.searchParams)
  const response = await fetch(url, {
    method: options.method ?? "GET",
    headers: options.body === undefined ? undefined : { "Content-Type": "application/json" },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: options.signal,
  })
  if (!response.ok) {
    throw new ApiError(response.status, await readErrorMessage(response))
  }
  return response.json() as Promise<T>
}

/** Build a full request URL, appending any defined `searchParams` as a query string. */
function buildUrl(path: string, searchParams?: Record<string, string | number | undefined>): string {
  const url = new URL(`${API_BASE_URL}${path}`)
  for (const [key, value] of Object.entries(searchParams ?? {})) {
    if (value !== undefined) url.searchParams.set(key, String(value))
  }
  return url.toString()
}

/** Extract FastAPI's `{"detail": "..."}` error shape, falling back to the status text. */
async function readErrorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json()
    if (typeof body?.detail === "string") return body.detail
    return JSON.stringify(body?.detail ?? body)
  } catch {
    return response.statusText || `Request failed with status ${response.status}`
  }
}
