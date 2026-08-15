import type { ReactNode } from "react"
import type { LucideIcon } from "lucide-react"

interface EmptyStateProps {
  icon: LucideIcon
  title: string
  description: string
  action?: ReactNode
}

/** Shown when a screen has nothing to display yet (e.g. no courses added), framed
 * as an invitation to act rather than a dead end. */
export function EmptyState({ icon: Icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="glass-inset flex flex-col items-center gap-3 rounded-xl border-dashed p-8 text-center">
      <Icon className="size-8 text-muted-foreground" aria-hidden="true" />
      <div className="space-y-1">
        <p className="font-semibold">{title}</p>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
      {action}
    </div>
  )
}
