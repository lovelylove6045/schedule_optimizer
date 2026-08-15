import { AlertTriangle, Info, TriangleAlert } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useTermsQuery } from "@/hooks/use-terms"
import type { DegreePlanOut } from "@/lib/types"
import { cn } from "@/lib/utils"

interface PlanSummaryCardProps {
  plan: DegreePlanOut
}

/** Header stats + messages for one plan: status, credit totals, projected
 * graduation term, and any INFO/WARNING/ERROR notes from the optimizer. */
export function PlanSummaryCard({ plan }: PlanSummaryCardProps) {
  const termsQuery = useTermsQuery()
  const graduationTerm = termsQuery.data?.find((term) => term.term_id === plan.projected_graduation_term_id)
  const isInfeasible = plan.status === "INFEASIBLE"
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle>{plan.plan_name ?? `Plan #${plan.degree_plan_id}`}</CardTitle>
          <Badge
            variant={isInfeasible ? "destructive" : "default"}
            className={cn(!isInfeasible && "bg-success text-success-foreground")}
          >
            {plan.status}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Stat label="Total credits" value={plan.total_credit_hours ?? "—"} />
          <Stat label="Extra credits" value={plan.additional_credit_hours ?? "—"} />
          <Stat label="Projected graduation" value={graduationTerm?.term_code ?? "—"} />
          <Stat label="Courses planned" value={plan.courses.length} />
        </dl>
        {plan.messages.length > 0 ? (
          <ul className="space-y-2">
            {plan.messages.map((message) => (
              <MessageRow key={message.optimization_message_id} severity={message.severity} text={message.message_text} />
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
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="font-mono text-lg font-semibold">{value}</dd>
    </div>
  )
}

/** One optimization_messages row, styled and iconed by its severity. */
function MessageRow({ severity, text }: { severity: string; text: string }) {
  const Icon = severity === "ERROR" ? AlertTriangle : severity === "WARNING" ? TriangleAlert : Info
  return (
    <li
      className={cn(
        "flex items-start gap-2 rounded-md border p-2.5 text-sm",
        severity === "ERROR" && "border-destructive/30 bg-destructive/5 text-destructive",
        severity === "WARNING" && "border-warning/30 bg-warning/5 text-warning",
        severity === "INFO" && "border-border bg-muted/50 text-muted-foreground",
      )}
    >
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <span>{text}</span>
    </li>
  )
}
