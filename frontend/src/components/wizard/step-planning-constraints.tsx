import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ErrorState } from "@/components/shared/error-state"
import { LoadingState } from "@/components/shared/loading-state"
import { Label } from "@/components/ui/label"
import { Slider } from "@/components/ui/slider"
import { Switch } from "@/components/ui/switch"
import { useTermsQuery } from "@/hooks/use-terms"
import { useScenarioBuilder } from "@/state/scenario-builder-context"

const MIN_CREDITS_RANGE: [number, number] = [3, 21]
const MAX_CREDITS_RANGE: [number, number] = [3, 21]

/** Screen 4: per-term credit-hour bounds, summer eligibility, and which
 * upcoming terms to exclude entirely (e.g. a planned co-op or study-abroad term). */
export function StepPlanningConstraints() {
  const { draft, dispatch } = useScenarioBuilder()
  const termsQuery = useTermsQuery()
  if (termsQuery.isPending) return <LoadingState label="Loading terms…" />
  if (termsQuery.isError) return <ErrorState message="Couldn't load terms from the server." />
  const upcomingTerms = draft.startTermId
    ? termsQuery.data.filter((term) => {
        const start = termsQuery.data.find((t) => t.term_id === draft.startTermId)
        return start ? term.sequence_index >= start.sequence_index : true
      })
    : termsQuery.data
  return (
    <Card>
      <CardHeader>
        <CardTitle>How much can you take on?</CardTitle>
        <CardDescription>Set a comfortable credit-hour range and which terms are off the table.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-8">
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <Label>Minimum credits per term</Label>
            <span className="font-mono text-sm text-muted-foreground">{draft.defaultMinimumCredits}</span>
          </div>
          <Slider
            min={MIN_CREDITS_RANGE[0]}
            max={MIN_CREDITS_RANGE[1]}
            step={1}
            value={[draft.defaultMinimumCredits ?? 12]}
            onValueChange={([value]) => dispatch({ type: "SET_MIN_CREDITS", value })}
          />
        </div>
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <Label>Maximum credits per term</Label>
            <span className="font-mono text-sm text-muted-foreground">{draft.defaultMaximumCredits}</span>
          </div>
          <Slider
            min={MAX_CREDITS_RANGE[0]}
            max={MAX_CREDITS_RANGE[1]}
            step={1}
            value={[draft.defaultMaximumCredits ?? 18]}
            onValueChange={([value]) => dispatch({ type: "SET_MAX_CREDITS", value })}
          />
        </div>
        <div className="flex items-center justify-between rounded-lg border p-4">
          <div>
            <Label htmlFor="allow-summer">Allow summer terms</Label>
            <p className="text-xs text-muted-foreground">Let the plan schedule courses in summer if it helps.</p>
          </div>
          <Switch
            id="allow-summer"
            checked={draft.allowSummer}
            onCheckedChange={(checked) => dispatch({ type: "TOGGLE_SUMMER", allow: checked })}
          />
        </div>
        <div className="space-y-2">
          <Label>Exclude specific terms (e.g. co-op or study abroad)</Label>
          <div className="grid gap-2 sm:grid-cols-2">
            {upcomingTerms.map((term) => (
              <label
                key={term.term_id}
                className="flex items-center justify-between gap-3 rounded-lg border p-3 text-sm"
              >
                <span>{term.term_code}</span>
                <Switch
                  checked={draft.excludedTermIds.includes(term.term_id)}
                  onCheckedChange={() => dispatch({ type: "TOGGLE_EXCLUDED_TERM", termId: term.term_id })}
                />
              </label>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
