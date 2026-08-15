import type { ReactNode } from "react"
import { GraduationCap } from "lucide-react"

interface AppShellProps {
  children: ReactNode
}

/** Shared page chrome (header + centered content column) for every route. */
export function AppShell({ children }: AppShellProps) {
  return (
    <div className="min-h-svh bg-background">
      <header className="border-b bg-primary text-primary-foreground">
        <div className="mx-auto flex max-w-6xl items-center gap-2 px-4 py-3 sm:px-6">
          <GraduationCap className="size-6 shrink-0" aria-hidden="true" />
          <div>
            <p className="text-sm font-extrabold tracking-tight sm:text-base">Degree Path Planner</p>
            <p className="text-xs text-primary-foreground/70">Academic Degree Optimization Engine</p>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-8">{children}</main>
    </div>
  )
}
