import { Check } from "lucide-react"
import { cn } from "@/lib/utils"

export type TermRibbonItemState = "completed" | "current" | "upcoming"

export interface TermRibbonItem {
  id: string | number
  label: string
  sublabel?: string
  state: TermRibbonItemState
}

interface TermRibbonProps {
  items: TermRibbonItem[]
  className?: string
}

/**
 * The signature visual element of the app: a horizontal pill stepper used both
 * as the wizard's 5-step progress indicator (Screens 1-5) and, restyled, as
 * the semester board's column headers (Screen 6) -- foreshadowing the plan's
 * term-by-term shape from the very first screen.
 */
export function TermRibbon({ items, className }: TermRibbonProps) {
  return (
    <ol className={cn("flex items-start gap-2 overflow-x-auto pb-1", className)}>
      {items.map((item, index) => (
        <li key={item.id} className="flex items-center gap-2">
          <TermRibbonPill item={item} />
          {index < items.length - 1 ? (
            <div
              className={cn(
                "h-0.5 w-6 shrink-0 rounded-full sm:w-10",
                item.state === "completed" ? "bg-success" : "bg-border",
              )}
              aria-hidden="true"
            />
          ) : null}
        </li>
      ))}
    </ol>
  )
}

/** Render one ribbon step's circular marker plus its label/sublabel underneath. */
function TermRibbonPill({ item }: { item: TermRibbonItem }) {
  return (
    <div className="flex flex-col items-center gap-1 text-center">
      <div
        className={cn(
          "flex size-9 shrink-0 items-center justify-center rounded-full border-2 font-mono text-sm font-semibold transition-colors",
          item.state === "completed" && "border-success bg-success text-success-foreground",
          item.state === "current" && "border-gold bg-gold text-gold-foreground ring-4 ring-gold/25",
          item.state === "upcoming" && "border-border bg-background text-muted-foreground",
        )}
      >
        {item.state === "completed" ? <Check className="size-4" aria-hidden="true" /> : item.label.slice(0, 2)}
      </div>
      <div className="w-16 sm:w-20">
        <p
          className={cn(
            "truncate text-xs font-medium",
            item.state === "upcoming" ? "text-muted-foreground" : "text-foreground",
          )}
        >
          {item.label}
        </p>
        {item.sublabel ? <p className="truncate text-[0.65rem] text-muted-foreground">{item.sublabel}</p> : null}
      </div>
    </div>
  )
}
