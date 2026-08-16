import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { ALL_OBJECTIVES, useScenarioBuilder } from "@/state/scenario-builder-context"
import { OBJECTIVE_LABELS } from "@/lib/objective-labels"
import type { OptimizationObjectiveType } from "@/lib/types"

/** Step 7: choose one required primary goal and up to two optional secondary priorities. */
export function StepObjectiveSelection() {
  const { draft, dispatch } = useScenarioBuilder()
  const primary = draft.objectiveOrder[0]
  const secondaryOne = draft.objectiveOrder[1]
  const secondaryTwo = draft.objectiveOrder[2]
  /** Replace one priority slot while keeping the ordered list unique. */
  function setPriority(index: number, value: OptimizationObjectiveType | "NONE") {
    const next = [...draft.objectiveOrder]
    if (value === "NONE") next.splice(index)
    else next[index] = value
    const unique = next.filter((item, position) => next.indexOf(item) === position)
    dispatch({ type: "SET_OBJECTIVE_ORDER", order: unique })
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>What matters most to you?</CardTitle>
        <CardDescription>
          Choose one primary goal. Secondary priorities are optional and apply in order without weakening a higher
          priority.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <PrioritySelect label="Primary goal" value={primary} onChange={(value) => setPriority(0, value)} required />
        <PrioritySelect label="Secondary priority #1" value={secondaryOne} onChange={(value) => setPriority(1, value)} />
        <PrioritySelect label="Secondary priority #2" value={secondaryTwo} onChange={(value) => setPriority(2, value)} />
        <p className="rounded-lg border bg-muted/30 p-3 text-xs text-muted-foreground">
          Credit caps, unavailable terms, required courses, and summer availability remain mandatory constraints—not
          optimization goals.
        </p>
      </CardContent>
    </Card>
  )
}

interface PrioritySelectProps {
  label: string
  value?: OptimizationObjectiveType
  onChange: (value: OptimizationObjectiveType | "NONE") => void
  required?: boolean
}

/** Render one ordered optimization-priority selector with its explanation. */
function PrioritySelect({ label, value, onChange, required = false }: PrioritySelectProps) {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      <Select value={value ?? "NONE"} onValueChange={(next) => onChange(next as OptimizationObjectiveType | "NONE")}>
        <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
        <SelectContent>
          {!required ? <SelectItem value="NONE">No additional priority</SelectItem> : null}
          {ALL_OBJECTIVES.map((objective) => (
            <SelectItem key={objective} value={objective}>{OBJECTIVE_LABELS[objective].title}</SelectItem>
          ))}
        </SelectContent>
      </Select>
      {value ? <p className="text-xs text-muted-foreground">{OBJECTIVE_LABELS[value].description}</p> : null}
    </div>
  )
}
