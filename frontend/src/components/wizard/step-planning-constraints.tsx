import { GraduationCap, TriangleAlert } from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ErrorState } from "@/components/shared/error-state"
import { LoadingState } from "@/components/shared/loading-state"
import { Badge } from "@/components/ui/badge"
import { Label } from "@/components/ui/label"
import { Slider } from "@/components/ui/slider"
import { Switch } from "@/components/ui/switch"
import { useTermsQuery } from "@/hooks/use-terms"
import { useScenarioBuilder } from "@/state/scenario-builder-context"
import { cn } from "@/lib/utils"
import type { TermOut } from "@/lib/types"

const CREDITS_RANGE: [number, number] = [3, 21]
/** Full-time undergraduate load, shown as a reference point on the sliders. */
const FULL_TIME_CREDITS = 12

/** Step 6: per-term credit-hour bounds, summer eligibility, and which upcoming terms
 * to exclude entirely (e.g. a planned co-op or study-abroad term). */
export function StepPlanningConstraints() {
  const { draft, dispatch } = useScenarioBuilder()
  const termsQuery = useTermsQuery()
  if (termsQuery.isPending) return <LoadingState label="Loading terms…" />
  if (termsQuery.isError) return <ErrorState message="Couldn't load terms from the server." />
  const startTerm = termsQuery.data.find((term) => term.term_id === draft.startTermId)
  const upcomingTerms = startTerm
    ? termsQuery.data.filter((term) => term.sequence_index >= startTerm.sequence_index)
    : termsQuery.data
  const minCredits = draft.defaultMinimumCredits ?? CREDITS_RANGE[0]
  const maxCredits = draft.defaultMaximumCredits ?? CREDITS_RANGE[1]
  const isInverted = minCredits > maxCredits
  return (
    <Card>
      <CardHeader>
        <CardTitle>How much can you take on?</CardTitle>
        <CardDescription>Set a comfortable credit-hour range and which terms are off the table.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <CreditConstraintControls
          minCredits={minCredits}
          maxCredits={maxCredits}
          isInverted={isInverted}
          allowSummer={draft.allowSummer}
          summerMaximumCredits={draft.summerMaximumCredits}
          enforceCreditMinimum={draft.enforceProgramCreditMinimum}
          onMinChange={(value) => dispatch({ type: "SET_MIN_CREDITS", value })}
          onMaxChange={(value) => dispatch({ type: "SET_MAX_CREDITS", value })}
          onSummerChange={(allow) => dispatch({ type: "TOGGLE_SUMMER", allow })}
          onSummerMaximumChange={(value) => dispatch({ type: "SET_SUMMER_MAX_CREDITS", value })}
          onCreditMinimumChange={(enforce) => dispatch({ type: "TOGGLE_CREDIT_MINIMUM", enforce })}
        />
        <ExcludedTermPicker
          terms={upcomingTerms}
          excludedTermIds={draft.excludedTermIds}
          onToggle={(termId) => dispatch({ type: "TOGGLE_EXCLUDED_TERM", termId })}
        />
      </CardContent>
    </Card>
  )
}

interface CreditConstraintControlsProps {
  minCredits: number
  maxCredits: number
  isInverted: boolean
  allowSummer: boolean
  summerMaximumCredits: number
  enforceCreditMinimum: boolean
  onMinChange: (value: number) => void
  onMaxChange: (value: number) => void
  onSummerChange: (allow: boolean) => void
  onSummerMaximumChange: (value: number) => void
  onCreditMinimumChange: (enforce: boolean) => void
}

/** Render regular/summer load controls and the published-degree floor toggle. */
function CreditConstraintControls(props: CreditConstraintControlsProps) {
  return (
    <>
      <div className="glass-inset space-y-6 rounded-xl p-4">
        <CreditSlider id="min-credits" label="Minimum credits per term" hint={props.minCredits >= FULL_TIME_CREDITS ? "Full-time load" : "Below full-time"} value={props.minCredits} onChange={props.onMinChange} />
        <CreditSlider id="max-credits" label="Maximum credits per term" hint={props.maxCredits > 18 ? "Heavy — usually needs approval" : "Typical ceiling"} value={props.maxCredits} onChange={props.onMaxChange} />
        {props.isInverted ? <p className="flex items-center gap-2 text-xs text-destructive"><TriangleAlert className="size-3.5 shrink-0" aria-hidden="true" />Your minimum is above your maximum — no term could satisfy both.</p> : null}
      </div>
      <label className="glass-inset flex items-center justify-between gap-3 rounded-xl p-4">
        <span><Label htmlFor="allow-summer">Allow summer terms</Label><span className="block text-xs text-muted-foreground">Let the plan schedule courses in summer if it shortens your timeline.</span></span>
        <Switch id="allow-summer" checked={props.allowSummer} onCheckedChange={props.onSummerChange} />
      </label>
      {props.allowSummer ? <div className="glass-inset rounded-xl p-4"><CreditSlider id="summer-max-credits" label="Maximum summer credits" hint="9 credits recommended" value={props.summerMaximumCredits} range={[0, 18]} onChange={props.onSummerMaximumChange} /></div> : null}
      <label className="flex items-start justify-between gap-4 rounded-xl border border-gold/40 bg-gold/10 p-4 shadow-[0_0_0_1px_var(--gold)_inset] shadow-gold/5">
        <span className="flex items-start gap-3">
          <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full bg-gold/20 text-gold"><GraduationCap className="size-4" aria-hidden="true" /></span>
          <span><span className="flex flex-wrap items-center gap-2"><Label htmlFor="enforce-credit-minimum" className="font-semibold">Require your major's full credit total</Label><Badge className="bg-gold text-gold-foreground">Recommended</Badge></span><span className="mt-1 block text-xs text-muted-foreground">Keeps your plan at or above the degree-applicable credit hours your major requires. Turn this off only if it prevents generation.</span></span>
        </span>
        <Switch id="enforce-credit-minimum" checked={props.enforceCreditMinimum} onCheckedChange={props.onCreditMinimumChange} className="mt-0.5 shrink-0 data-[state=checked]:bg-gold" />
      </label>
    </>
  )
}

/** Let the student exclude unavailable planning terms. */
function ExcludedTermPicker({ terms, excludedTermIds, onToggle }: {
  terms: TermOut[]
  excludedTermIds: number[]
  onToggle: (termId: number) => void
}) {
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Label>Terms you can't enroll (co-op, study abroad, leave)</Label>
        {excludedTermIds.length > 0 ? <Badge variant="secondary" className="font-mono text-[0.7rem]">{excludedTermIds.length} excluded</Badge> : null}
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        {terms.map((term) => {
          const isExcluded = excludedTermIds.includes(term.term_id)
          return <label key={term.term_id} className={cn("glass-inset flex items-center justify-between gap-3 rounded-lg p-3 text-sm", isExcluded && "border-warning/50 bg-warning/10")}><span className="font-mono text-xs">{term.term_code}</span><Switch checked={isExcluded} aria-label={`Exclude ${term.term_code}`} onCheckedChange={() => onToggle(term.term_id)} /></label>
        })}
      </div>
    </div>
  )
}

interface CreditSliderProps {
  id: string
  label: string
  hint: string
  value: number
  range?: [number, number]
  onChange: (value: number) => void
}

/** One credit-hour slider with its live value and a plain-language hint. */
function CreditSlider({ id, label, hint, value, range = CREDITS_RANGE, onChange }: CreditSliderProps) {
  return (
    <div className="space-y-3">
      <div className="flex items-baseline justify-between gap-2">
        <Label htmlFor={id}>{label}</Label>
        <span className="flex items-baseline gap-2">
          <span className="text-[0.7rem] text-muted-foreground">{hint}</span>
          <span className="font-mono text-lg font-semibold">{value}</span>
        </span>
      </div>
      <Slider
        id={id}
        min={range[0]}
        max={range[1]}
        step={1}
        value={[value]}
        onValueChange={([next]) => onChange(next)}
      />
    </div>
  )
}
