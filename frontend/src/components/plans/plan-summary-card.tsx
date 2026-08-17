import { AlertTriangle, Info, TriangleAlert } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { useTermsQuery } from "@/hooks/use-terms"
import { OBJECTIVE_LABELS } from "@/lib/objective-labels"
import type { DegreePlanOut, OptimizationMessageOut, OptimizationObjectiveType } from "@/lib/types"
import { cn } from "@/lib/utils"

/** Severity order for the message list: problems first, notes last. */
const SEVERITY_RANK: Record<string, number> = { ERROR: 0, WARNING: 1, INFO: 2 }

interface PlanSummaryCardProps {
  plan: DegreePlanOut
}

/** Header stats + messages for one plan: status, credit totals, projected graduation
 * term, and any INFO/WARNING/ERROR notes from the optimizer. */
export function PlanSummaryCard({ plan }: PlanSummaryCardProps) {
  const termsQuery = useTermsQuery()
  const graduationTerm = termsQuery.data?.find((term) => term.term_id === plan.projected_graduation_term_id)
  const isInfeasible = plan.status === "INFEASIBLE"
  const needsAttention = plan.status === "VALID_WITH_WARNINGS"
  const objective = OBJECTIVE_LABELS[plan.plan_name as OptimizationObjectiveType]
  const messages = [...plan.messages].sort(
    (a, b) => (SEVERITY_RANK[a.severity] ?? 3) - (SEVERITY_RANK[b.severity] ?? 3),
  )
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <CardTitle>{objective?.title ?? plan.plan_name ?? `Plan #${plan.degree_plan_id}`}</CardTitle>
            {objective ? <CardDescription>{objective.description}</CardDescription> : null}
          </div>
          <Badge
            variant={isInfeasible ? "destructive" : needsAttention ? "outline" : "default"}
            className={cn(
              !isInfeasible && !needsAttention && "bg-success text-success-foreground",
              needsAttention && "border-amber-400 bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-200",
            )}
          >
            {isInfeasible ? "Not possible" : needsAttention ? "Needs attention" : plan.solver_status === "OPTIMAL" ? "Optimized" : "Best solution found"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Degree-applicable credits" value={plan.total_credit_hours ?? "—"} />
          <Stat label="Scheduled workload credits" value={plan.scheduled_credit_hours ?? "—"} />
          <Stat label="Extra credits" value={plan.additional_credit_hours ?? "—"} />
          <Stat label="Projected graduation" value={graduationTerm?.term_code ?? "—"} />
          <Stat label="Courses planned" value={plan.courses.length} />
        </dl>
        {messages.length > 0 ? (
          <ul className="space-y-2">
            {messages.map((message) => (
              <MessageRow key={message.optimization_message_id} message={message} />
            ))}
          </ul>
        ) : null}
      </CardContent>
    </Card>
  )
}

/** One labeled number in the plan's stat grid. */
function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="glass-inset rounded-lg p-3">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="font-mono text-lg font-semibold">{value}</dd>
    </div>
  )
}

/** One optimization_messages row, styled and iconed by its severity. */
function MessageRow({ message }: { message: OptimizationMessageOut }) {
  const { severity, message_text } = message
  const Icon = severity === "ERROR" ? AlertTriangle : severity === "WARNING" ? TriangleAlert : Info
  return (
    <li
      className={cn(
        "flex items-start gap-2 rounded-lg border p-3 text-sm",
        severity === "ERROR" && "border-destructive/30 bg-destructive/10 text-destructive",
        severity === "WARNING" && "border-warning/40 bg-warning/10 text-warning",
        severity === "INFO" && "border-border bg-muted/40 text-muted-foreground",
      )}
    >
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <span className="min-w-0">
        <span className="block font-medium">{messageHeadline(message)}</span>
        <span className="block text-xs opacity-90">{message_text}</span>
      </span>
    </li>
  )
}

/** A short heading for a message, keyed off its stable `message_code`, so a reader
 * can tell at a glance whether it needs action or is just a caveat. */
function messageHeadline(message: OptimizationMessageOut): string {
  switch (message.message_code) {
    case "INFEASIBLE":
      return "This combination can't be scheduled"
    case "SUGGESTED_ADJUSTMENTS":
      return "Try relaxing one of these"
    case "ADVISOR_SIGNOFF_NEEDED":
      return "Needs advisor sign-off"
    case "PREREQUISITE_NOT_MODELED":
      return "Prerequisites to verify yourself"
    case "UNVERIFIED_PREREQUISITE_TYPE":
      return "Assumed satisfied"
    case "OVERLAP_POLICY_UNVERIFIED":
      return "Sharing policy needs verification"
    case "SOLVER_DEADLINE_REACHED":
      return "Best solution within time limit"
    case "TERM_CREDIT_BELOW_MINIMUM":
      return "Term is below your credit minimum"
    case "TERM_CREDIT_ABOVE_MAXIMUM":
      return "Term is above your credit maximum"
    case "OBJECTIVE_STAGE_RESULTS":
      return "Optimization proof status"
    case "PROTOTYPE_DISCLAIMER":
      return "Prototype planning notice"
    default:
      return message.severity === "ERROR" ? "Problem" : "Note"
  }
}
