import { Dot } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { requirementNodeLabel } from "@/lib/requirement-node-label"
import type { RequirementNodeOut, RequirementSetOut } from "@/lib/types"

interface CatalogRequirementTreeProps {
  requirementSets: RequirementSetOut[]
}

/** A program's raw requirement sets (no plan/student context), for the catalog
 * browser's program detail panel -- the same tree shape the optimizer itself
 * reads, minus `is_satisfied`/`is_shared` which only exist against a real plan. */
export function CatalogRequirementTree({ requirementSets }: CatalogRequirementTreeProps) {
  return (
    <div className="space-y-4">
      {requirementSets.map((requirementSet) => (
        <CatalogRequirementSetSection key={requirementSet.requirement_set_id} requirementSet={requirementSet} />
      ))}
    </div>
  )
}

/** One requirement_set's header plus its top-level node rows. */
function CatalogRequirementSetSection({ requirementSet }: { requirementSet: RequirementSetOut }) {
  return (
    <div className="overflow-hidden rounded-xl border bg-background/40">
      <div className="border-b px-4 py-2.5">
        <p className="text-sm font-semibold">{requirementSet.requirement_set_name}</p>
        {requirementSet.description ? (
          <p className="text-xs text-muted-foreground">{requirementSet.description}</p>
        ) : null}
      </div>
      <ul className="divide-y">
        {requirementSet.nodes.map((node) => (
          <CatalogRequirementNodeRow key={node.requirement_node_id} node={node} depth={0} />
        ))}
      </ul>
    </div>
  )
}

/** One requirement node's row (label, credit/count badge, source text) plus its indented children. */
function CatalogRequirementNodeRow({ node, depth }: { node: RequirementNodeOut; depth: number }) {
  return (
    <li>
      <div className="flex items-start gap-2 px-4 py-2.5" style={{ paddingLeft: `${1 + depth * 1.25}rem` }}>
        <Dot className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="text-sm">{requirementNodeLabel(node)}</p>
          {node.source_text ? <p className="text-xs text-muted-foreground">{node.source_text}</p> : null}
        </div>
        {node.required_course ? (
          <Badge variant="outline" className="shrink-0">
            {node.required_course.credit_hours} cr
          </Badge>
        ) : null}
      </div>
      {node.children.length > 0 ? (
        <ul className="divide-y">
          {node.children.map((child) => (
            <CatalogRequirementNodeRow key={child.requirement_node_id} node={child} depth={depth + 1} />
          ))}
        </ul>
      ) : null}
    </li>
  )
}
