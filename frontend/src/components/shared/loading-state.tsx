import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"

interface LoadingStateProps {
  label?: string
  rows?: number
  className?: string
}

/** A skeleton block used while a screen's data is still loading, so nothing renders blank. */
export function LoadingState({ label, rows = 3, className }: LoadingStateProps) {
  return (
    <div className={cn("space-y-3", className)} role="status" aria-live="polite">
      {label ? <p className="text-sm text-muted-foreground">{label}</p> : null}
      {Array.from({ length: rows }).map((_, index) => (
        <Skeleton key={index} className="h-14 w-full" />
      ))}
    </div>
  )
}
