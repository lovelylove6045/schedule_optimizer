import { BookOpen, GraduationCap } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { EmptyState } from "@/components/shared/empty-state"
import { ErrorState } from "@/components/shared/error-state"
import { LoadingState } from "@/components/shared/loading-state"
import { CatalogRequirementTree } from "@/components/catalog/catalog-requirement-tree"
import { useProgramRequirementsQuery } from "@/hooks/use-programs"
import type { ProgramOut } from "@/lib/types"

interface CatalogProgramDetailProps {
  program: ProgramOut | undefined
}

/** The right-hand column of the catalog browser: the selected program's own
 * facts (college, department, type, total credits) plus its full requirement
 * tree, straight from `schedule_optimizer_db`'s requirement_nodes via the same
 * `/programs/{id}/requirements` endpoint the optimizer itself resolves. */
export function CatalogProgramDetail({ program }: CatalogProgramDetailProps) {
  const requirementsQuery = useProgramRequirementsQuery(program?.academic_program_id ?? null)
  if (!program) {
    return (
      <EmptyState
        icon={GraduationCap}
        title="Pick a program"
        description="Select a major, minor, emphasis, or certificate on the left to see its full requirements."
      />
    )
  }
  return (
    <div className="space-y-4">
      <CatalogProgramHeader program={program} />
      {requirementsQuery.isPending ? <LoadingState label="Loading requirements…" /> : null}
      {requirementsQuery.isError ? (
        <ErrorState message="Couldn't load this program's requirements." onRetry={() => requirementsQuery.refetch()} />
      ) : null}
      {requirementsQuery.data && requirementsQuery.data.length === 0 ? (
        <EmptyState
          icon={BookOpen}
          title="No requirement sets on file"
          description="This program doesn't have any linked requirement sets in the catalog yet."
        />
      ) : null}
      {requirementsQuery.data && requirementsQuery.data.length > 0 ? (
        <CatalogRequirementTree requirementSets={requirementsQuery.data} />
      ) : null}
    </div>
  )
}

/** The selected program's name plus its college/department/type/credit facts. */
function CatalogProgramHeader({ program }: { program: ProgramOut }) {
  const facts = [program.college_name, program.department_name, program.program_code].filter(Boolean)
  return (
    <div className="space-y-2 border-b pb-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-semibold">{program.program_name}</h2>
        <Badge className="bg-gold text-gold-foreground">{program.program_type}</Badge>
        {!program.is_active ? <Badge variant="destructive">Inactive</Badge> : null}
      </div>
      <p className="text-sm text-muted-foreground">{facts.join(" · ")}</p>
      {program.total_credit_hours ? (
        <p className="text-sm">
          <span className="font-medium">{program.total_credit_hours}</span> credit hours to graduate
        </p>
      ) : null}
    </div>
  )
}
