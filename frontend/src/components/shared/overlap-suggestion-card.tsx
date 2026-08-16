import { Loader2, Plus } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import type { ProgramOverlapOut } from "@/lib/types"

interface OverlapSuggestionCardProps {
  suggestion: ProgramOverlapOut
  onAdd: (programId: number) => void
  isAdding?: boolean
}

/** One suggested program with its shared-course count/credits and a one-tap
 * add action -- used both by the wizard's "any other goals?" step and the
 * results page's post-generation/post-swap overlap panel. */
export function OverlapSuggestionCard({ suggestion, onAdd, isAdding = false }: OverlapSuggestionCardProps) {
  const coursesLabel = `${suggestion.overlap_course_count} course${suggestion.overlap_course_count === 1 ? "" : "s"}`
  return (
    <div className="flex items-start justify-between gap-3 rounded-lg border bg-background/40 p-3">
      <div className="min-w-0">
        <p className="truncate text-sm font-medium">{suggestion.program_name}</p>
        <Badge variant="outline" className="mt-1.5">
          Estimated overlap: {coursesLabel} · {suggestion.overlap_credit_hours} cr
        </Badge>
      </div>
      <Button
        type="button"
        variant="secondary"
        size="icon-sm"
        aria-label={`Add ${suggestion.program_name}`}
        disabled={isAdding}
        onClick={() => onAdd(suggestion.academic_program_id)}
      >
        {isAdding ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : <Plus className="size-4" aria-hidden="true" />}
      </Button>
    </div>
  )
}
