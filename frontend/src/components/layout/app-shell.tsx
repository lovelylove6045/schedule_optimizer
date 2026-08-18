import type { ReactNode } from "react"
import { BookOpen, GitBranch, GraduationCap } from "lucide-react"
import { Link, useLocation } from "react-router-dom"
import { useIsMutating } from "@tanstack/react-query"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

interface AppShellProps {
  children: ReactNode
}

/** Shared page chrome for every route: the fixed aurora backdrop the frosted
 * surfaces blur against, a glass header, and a centered content column. */
export function AppShell({ children }: AppShellProps) {
  const { pathname } = useLocation()
  const alternativesGenerating = useIsMutating({ mutationKey: ["generate-alternatives"] }) > 0
  const isResultsRoute = pathname.startsWith("/plans/")
  const isCatalogRoute = pathname.startsWith("/catalog")
  const isCoursesRoute = pathname.startsWith("/courses")
  return (
    <div className="relative min-h-svh">
      <div className="app-aurora" aria-hidden="true" />
      <header className="glass-panel sticky top-0 z-40 !rounded-none !border-x-0 !border-t-0">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-3 sm:px-6">
          <Link to="/" className="flex items-center gap-3 rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-ring">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm">
              <GraduationCap className="size-5" aria-hidden="true" />
            </span>
            <span>
              <span className="block text-sm font-extrabold tracking-tight sm:text-base">Degree Path Planner</span>
              <span className="block text-xs text-muted-foreground">Academic Degree Optimization Engine</span>
            </span>
          </Link>
          <Link
            to="/catalog"
            className={cn(
              "ml-auto flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors hover:bg-accent/40",
              isCatalogRoute ? "bg-accent/60 text-foreground" : "text-muted-foreground",
            )}
          >
            <BookOpen className="size-4" aria-hidden="true" />
            <span className="hidden sm:inline">Catalog</span>
          </Link>
          {alternativesGenerating ? (
            <span title="Course prerequisites unlock when alternative generation finishes" aria-disabled="true" className="flex cursor-not-allowed items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium text-muted-foreground/45">
              <GitBranch className="size-4" aria-hidden="true" />
              <span className="hidden sm:inline">Courses</span>
            </span>
          ) : (
            <Link
              to="/courses"
              className={cn(
                "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors hover:bg-accent/40",
                isCoursesRoute ? "bg-accent/60 text-foreground" : "text-muted-foreground",
              )}
            >
              <GitBranch className="size-4" aria-hidden="true" />
              <span className="hidden sm:inline">Courses</span>
            </Link>
          )}
          {isResultsRoute ? (
            <Badge variant="outline" className="hidden sm:inline-flex">
              Results
            </Badge>
          ) : null}
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-10">{children}</main>
    </div>
  )
}
