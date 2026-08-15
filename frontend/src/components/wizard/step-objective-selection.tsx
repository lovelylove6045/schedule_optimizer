import { ArrowDown, ArrowUp } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { OBJECTIVE_LABELS } from "@/lib/objective-labels"
import { useScenarioBuilder } from "@/state/scenario-builder-context"

/** Screen 5: rank the 5 supported objectives by priority (1st = most important).
 * A plain ranked list with up/down buttons instead of drag-and-drop, per the
 * "otherwise a simple ranked list" fallback in the Phase 5 plan. */
export function StepObjectiveSelection() {
  const { draft, dispatch } = useScenarioBuilder()
  /** Swap the objective at `index` with its neighbor in `direction`, if one exists. */
  function move(index: number, direction: -1 | 1) {
    const target = index + direction
    if (target < 0 || target >= draft.objectiveOrder.length) return
    const reordered = [...draft.objectiveOrder]
    ;[reordered[index], reordered[target]] = [reordered[target], reordered[index]]
    dispatch({ type: "SET_OBJECTIVE_ORDER", order: reordered })
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>What matters most to you?</CardTitle>
        <CardDescription>
          Rank these from most to least important -- the top priority drives the recommended plan; the rest still
          generate alternatives to compare.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ol className="space-y-2">
          {draft.objectiveOrder.map((objectiveType, index) => (
            <li key={objectiveType} className="flex items-center gap-3 rounded-lg border p-3">
              <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary font-mono text-xs font-semibold text-primary-foreground">
                {index + 1}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">{OBJECTIVE_LABELS[objectiveType].title}</p>
                <p className="text-xs text-muted-foreground">{OBJECTIVE_LABELS[objectiveType].description}</p>
              </div>
              <div className="flex shrink-0 flex-col gap-1">
                <Button
                  variant="ghost"
                  size="icon-xs"
                  aria-label="Move up"
                  disabled={index === 0}
                  onClick={() => move(index, -1)}
                >
                  <ArrowUp className="size-3.5" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon-xs"
                  aria-label="Move down"
                  disabled={index === draft.objectiveOrder.length - 1}
                  onClick={() => move(index, 1)}
                >
                  <ArrowDown className="size-3.5" />
                </Button>
              </div>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  )
}
