import { useState, type ReactNode } from "react"
import { useLocation } from "react-router-dom"
import { AlertCircle, BookOpenCheck, Building2, CheckCircle2, ChevronRight, GitBranch, GraduationCap, LoaderCircle, Search, ShieldQuestion } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { CatalogSnapshotNotice } from "@/components/catalog/catalog-snapshot-notice"
import { ErrorState } from "@/components/shared/error-state"
import { LoadingState } from "@/components/shared/loading-state"
import { useCollegesQuery } from "@/hooks/use-colleges"
import { useCoursePrerequisitesQuery } from "@/hooks/use-course-prerequisites"
import { useCourseSearchQuery } from "@/hooks/use-course-search"
import { useProgramsQuery } from "@/hooks/use-programs"
import type { CourseOut, PrerequisiteNodeOut, ProgramOut, RequisiteType } from "@/lib/types"

type FilterOption = [number, string]

interface CoursesLocationState {
  course?: CourseOut
}

/** Present searchable catalog rules exactly as the prerequisite engine receives them. */
export function CoursesPage() {
  const location = useLocation()
  const initialCourse = (location.state as CoursesLocationState | null)?.course ?? null
  const collegesQuery = useCollegesQuery()
  const programsQuery = useProgramsQuery()
  const [collegeId, setCollegeId] = useState<number | null>(null)
  const [departmentId, setDepartmentId] = useState<number | null>(null)
  const [search, setSearch] = useState(initialCourse ? `${initialCourse.subject_code} ${initialCourse.course_number}` : "")
  const [selectedCourse, setSelectedCourse] = useState<CourseOut | null>(initialCourse)
  const courseSearchQuery = useCourseSearchQuery(search, { collegeId, departmentId })
  if (collegesQuery.isPending || programsQuery.isPending) return <LoadingState label="Loading prerequisite catalog…" rows={6} />
  if (collegesQuery.isError || programsQuery.isError) return <ErrorState message="Couldn't load prerequisite filters." />
  const departments = getDepartmentOptions(programsQuery.data, collegeId)
  const results = courseSearchQuery.data ?? []
  return (
    <div className="space-y-6">
      <PrerequisiteHeading />
      <CatalogSnapshotNotice />
      <section className="glass-panel overflow-hidden rounded-2xl">
        <PrerequisiteFilters
          colleges={collegesQuery.data.map((college) => [college.college_id, college.college_name])}
          departments={departments}
          collegeId={collegeId}
          departmentId={departmentId}
          search={search}
          onCollegeChange={(value) => {
            setCollegeId(value)
            setDepartmentId(null)
          }}
          onDepartmentChange={setDepartmentId}
          onSearchChange={setSearch}
        />
        <div className="grid min-h-[38rem] lg:grid-cols-[19rem_minmax(0,1fr)]">
          <CourseResults search={search} results={results} selectedCourseId={selectedCourse?.course_id ?? null} isFetching={courseSearchQuery.isFetching} isError={courseSearchQuery.isError} onSelect={setSelectedCourse} />
          <CoursePrerequisiteDetail course={selectedCourse} onSelectCourse={setSelectedCourse} />
        </div>
      </section>
    </div>
  )
}

/** Explain that this page exposes optimizer-interpreted academic rules. */
function PrerequisiteHeading() {
  return (
    <div className="space-y-1">
      <p className="text-xs font-semibold tracking-[0.18em] text-primary uppercase">Rule validation</p>
      <h1 className="text-3xl font-bold tracking-tight">Courses & prerequisites</h1>
      <p className="max-w-3xl text-muted-foreground">Search a course to inspect the prerequisites, co-requisites, recommendations, and external conditions used by the planning engine.</p>
    </div>
  )
}

interface PrerequisiteFiltersProps {
  colleges: FilterOption[]
  departments: FilterOption[]
  collegeId: number | null
  departmentId: number | null
  search: string
  onCollegeChange: (value: number | null) => void
  onDepartmentChange: (value: number | null) => void
  onSearchChange: (value: string) => void
}

/** Render school filters and the required remote course search input. */
function PrerequisiteFilters(props: PrerequisiteFiltersProps) {
  return (
    <div className="space-y-4 border-b bg-background/30 p-4 sm:p-5">
      <div className="grid gap-3 md:grid-cols-2">
        <FilterSelect label="College" allLabel="All colleges" icon={<Building2 className="size-4" />} options={props.colleges} value={props.collegeId} onChange={props.onCollegeChange} />
        <FilterSelect label="Department" allLabel="All departments" icon={<GraduationCap className="size-4" />} options={props.departments} value={props.departmentId} onChange={props.onDepartmentChange} />
      </div>
      <label className="space-y-1.5">
        <span className="text-xs font-medium text-muted-foreground">Course code, number, or title</span>
        <span className="relative block">
          <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
          <Input className="h-11 pl-10" value={props.search} onChange={(event) => props.onSearchChange(event.target.value)} placeholder='Search “STAT 3113”, “calculus”, or a course title' />
        </span>
      </label>
    </div>
  )
}

interface FilterSelectProps {
  label: string
  allLabel: string
  icon: ReactNode
  options: FilterOption[]
  value: number | null
  onChange: (value: number | null) => void
}

/** Render one native catalog filter with an explicit all-values option. */
function FilterSelect({ label, allLabel, icon, options, value, onChange }: FilterSelectProps) {
  return (
    <label className="space-y-1.5">
      <span className="text-xs font-medium text-muted-foreground">{label}</span>
      <span className="relative block">
        <span className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-muted-foreground">{icon}</span>
        <select className="h-11 w-full appearance-none rounded-lg border bg-background/70 pr-9 pl-10 text-sm outline-none focus:ring-2 focus:ring-ring/50" value={value ?? "ALL"} onChange={(event) => onChange(event.target.value === "ALL" ? null : Number(event.target.value))}>
          <option value="ALL">{allLabel}</option>
          {options.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
        </select>
        <span className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-xs text-muted-foreground">⌄</span>
      </span>
    </label>
  )
}

interface CourseResultsProps {
  search: string
  results: CourseOut[]
  selectedCourseId: number | null
  isFetching: boolean
  isError: boolean
  onSelect: (course: CourseOut) => void
}

/** Show filtered course matches with exact catalog codes and database ids. */
function CourseResults(props: CourseResultsProps) {
  const message = courseResultMessage(props)
  return (
    <aside className="border-b p-3 lg:border-r lg:border-b-0">
      <div className="mb-2 flex items-center justify-between px-2 py-1">
        <h2 className="text-sm font-semibold">Courses</h2>
        {props.results.length > 0 ? <span className="text-xs text-muted-foreground">{props.results.length} matches</span> : null}
      </div>
      {message ? <p className="rounded-lg bg-muted/40 p-4 text-sm text-muted-foreground">{message}</p> : null}
      <div className="max-h-[34rem] space-y-1 overflow-y-auto">
        {props.results.map((course) => (
          <button key={course.course_id} type="button" onClick={() => props.onSelect(course)} className={`w-full rounded-xl border p-3 text-left transition-colors hover:bg-accent/40 ${props.selectedCourseId === course.course_id ? "border-primary/40 bg-primary/8" : "border-transparent"}`}>
            <span className="flex items-start justify-between gap-2">
              <span className="font-mono text-xs font-bold text-primary">{course.subject_code} {course.course_number}</span>
              <span className="font-mono text-[0.65rem] text-muted-foreground">ID {course.course_id}</span>
            </span>
            <span className="mt-1 block text-sm leading-snug">{course.course_title}</span>
          </button>
        ))}
      </div>
    </aside>
  )
}

/** Return contextual empty/loading/error text for the result list. */
function courseResultMessage(props: CourseResultsProps): string | null {
  if (props.search.trim().length < 2) return "Type at least two characters to search within the selected college or department."
  if (props.isFetching) return "Searching the catalog…"
  if (props.isError) return "The course search failed. Try again."
  if (props.results.length === 0) return "No courses matched this search and filter combination."
  return null
}

/** Render the selected course and its recursively discoverable rule chain. */
function CoursePrerequisiteDetail({ course, onSelectCourse }: { course: CourseOut | null; onSelectCourse: (course: CourseOut) => void }) {
  const prerequisitesQuery = useCoursePrerequisitesQuery(course?.course_id)
  if (!course) return <EmptyPrerequisiteDetail />
  const visibleNodes = prerequisitesQuery.data ? visiblePrerequisiteNodes(prerequisitesQuery.data) : []
  return (
    <article className="min-w-0 p-4 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-mono text-lg font-bold text-primary">{course.subject_code} {course.course_number}</h2>
            <Badge variant="outline">Database ID {course.course_id}</Badge>
            <Badge variant="secondary">{course.course_type.replaceAll("_", " ")}</Badge>
          </div>
          <p className="mt-1 text-xl font-semibold">{course.course_title}</p>
        </div>
        <span className="rounded-full border bg-background/60 px-3 py-1 font-mono text-xs">{course.credit_hours} credits</span>
      </div>
      <p className="mt-4 text-sm leading-relaxed text-muted-foreground">{course.course_description || "No catalog description is available."}</p>
      <div className="mt-6 border-t pt-5">
        <div className="mb-4 flex items-center gap-2">
          <GitBranch className="size-4 text-primary" aria-hidden="true" />
          <h3 className="font-semibold">Rules recognized by the optimizer</h3>
        </div>
        {prerequisitesQuery.isPending ? <RuleResolutionLoading course={course} /> : null}
        {prerequisitesQuery.isError ? <ErrorState message="Couldn't load this course's prerequisite rules." /> : null}
        {!prerequisitesQuery.isPending && !prerequisitesQuery.isError && visibleNodes.length === 0 ? <NoPrerequisites /> : null}
        {visibleNodes.length > 0 ? <RuleTree nodes={visibleNodes} depth={0} visitedCourseIds={new Set([course.course_id])} onSelectCourse={onSelectCourse} /> : null}
      </div>
    </article>
  )
}

/** Show the catalog-rule pipeline while the prerequisite endpoint is responding. */
function RuleResolutionLoading({ course }: { course: CourseOut }) {
  return (
    <div className="space-y-3 rounded-xl border bg-muted/20 p-4" role="status" aria-live="polite">
      <RuleLoadingStep icon={<CheckCircle2 className="size-4 text-emerald-600" />} label={`${course.subject_code} ${course.course_number} identified`} detail="Course identity and catalog description loaded" />
      <RuleLoadingStep icon={<LoaderCircle className="size-4 animate-spin text-primary" />} label="Reading the catalog rule tree" detail="Checking prerequisite and co-requisite branches" active />
      <RuleLoadingStep icon={<ShieldQuestion className="size-4" />} label="Classifying external conditions" detail="Placement exams, consent, and standing are shown separately" />
      <div className="h-1.5 overflow-hidden rounded-full bg-primary/10" aria-hidden="true"><div className="optimization-progress-sweep h-full w-2/5 rounded-full bg-gradient-to-r from-primary via-ring to-gold" /></div>
    </div>
  )
}

/** Render one concise step in prerequisite-rule resolution. */
function RuleLoadingStep({ icon, label, detail, active = false }: { icon: ReactNode; label: string; detail: string; active?: boolean }) {
  return (
    <div className={`flex items-start gap-3 rounded-lg p-2 ${active ? "bg-primary/7 text-foreground" : "text-muted-foreground"}`}>
      <span className="mt-0.5 shrink-0">{icon}</span>
      <span><span className="block text-sm font-semibold">{label}</span><span className="block text-xs">{detail}</span></span>
    </div>
  )
}

/** Prompt the user to choose a course before showing a rule tree. */
function EmptyPrerequisiteDetail() {
  return (
    <div className="flex min-h-[32rem] flex-col items-center justify-center p-8 text-center">
      <span className="flex size-14 items-center justify-center rounded-2xl bg-primary/10 text-primary"><BookOpenCheck className="size-7" /></span>
      <h2 className="mt-4 text-lg font-semibold">Select a course to validate</h2>
      <p className="mt-1 max-w-md text-sm text-muted-foreground">Its exact database identity, description, prerequisite choices, co-requisites, and dependency chain will appear here.</p>
    </div>
  )
}

/** Confirm that the catalog supplies no prerequisite or co-requisite rows. */
function NoPrerequisites() {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-emerald-900">
      <CheckCircle2 className="mt-0.5 size-5 shrink-0" />
      <div><p className="font-semibold">No prerequisites identified</p><p className="text-sm text-emerald-800">The current catalog snapshot contains no prerequisite or co-requisite rules for this course.</p></div>
    </div>
  )
}

interface RuleContextProps {
  depth: number
  visitedCourseIds: Set<number>
  onSelectCourse: (course: CourseOut) => void
  autoExpand?: boolean
}

interface RuleTreeProps extends RuleContextProps {
  nodes: PrerequisiteNodeOut[]
}

/** Render a list of prerequisite roots as independently required rule blocks. */
function RuleTree(props: RuleTreeProps) {
  return <div className="space-y-3">{props.nodes.map((node) => <RuleNode key={node.course_rule_node_id} node={node} {...props} />)}</div>
}

/** Dispatch a recognized rule node to a group, course dependency, or condition. */
function RuleNode({ node, depth, visitedCourseIds, onSelectCourse, autoExpand }: RuleContextProps & { node: PrerequisiteNodeOut }) {
  if (node.node_type === "GROUP") return <RuleGroup node={node} depth={depth} visitedCourseIds={visitedCourseIds} onSelectCourse={onSelectCourse} autoExpand={autoExpand} />
  if (node.node_type === "COURSE" && node.required_course) return <CourseDependency node={node} depth={depth} visitedCourseIds={visitedCourseIds} onSelectCourse={onSelectCourse} autoExpand={autoExpand} />
  return <ConditionRule node={node} />
}

/** Render an ALL/ANY/N_OF group after unavailable catalog-course branches are removed. */
function RuleGroup({ node, depth, visitedCourseIds, onSelectCourse, autoExpand = true }: RuleContextProps & { node: PrerequisiteNodeOut }) {
  const children = visiblePrerequisiteNodes(node.children)
  const expandChildren = autoExpand && children.length <= 4
  return (
    <section className="rounded-xl border bg-background/45 p-3 sm:p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Badge className={requisiteBadgeClass(node.requisite_type)}>{requisiteLabel(node.requisite_type)}</Badge>
        <span className="text-sm font-semibold">{groupInstruction(node, children.length)}</span>
      </div>
      <div className="space-y-2 border-l-2 border-primary/15 pl-3">
        {children.map((child) => <RuleNode key={child.course_rule_node_id} node={child} depth={depth} visitedCourseIds={visitedCourseIds} onSelectCourse={onSelectCourse} autoExpand={expandChildren} />)}
      </div>
    </section>
  )
}

/** Render one required course and recursively expose its own short dependency chain. */
function CourseDependency({ node, depth, visitedCourseIds, onSelectCourse, autoExpand = true }: RuleContextProps & { node: PrerequisiteNodeOut }) {
  const course = node.required_course as CourseOut
  const canExpand = autoExpand && depth < 3 && !visitedCourseIds.has(course.course_id)
  const nestedQuery = useCoursePrerequisitesQuery(canExpand ? course.course_id : undefined)
  const nestedNodes = nestedQuery.data ? visiblePrerequisiteNodes(nestedQuery.data) : []
  const nextVisited = new Set(visitedCourseIds).add(course.course_id)
  return (
    <div className="rounded-lg border bg-background/70 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <button type="button" className="font-mono text-xs font-bold text-primary hover:underline" onClick={() => onSelectCourse(course)}>{course.subject_code} {course.course_number}</button>
          <p className="mt-0.5 text-sm">{course.course_title}</p>
        </div>
        <div className="flex items-center gap-1.5">
          {node.minimum_grade ? <Badge variant="outline">Grade {node.minimum_grade}+</Badge> : null}
          <Badge className={requisiteBadgeClass(node.requisite_type)}>{requisiteLabel(node.requisite_type)}</Badge>
        </div>
      </div>
      {canExpand && nestedQuery.isPending ? <p className="mt-2 text-xs text-muted-foreground">Checking this course's prerequisites…</p> : null}
      {nestedNodes.length > 0 ? (
        <div className="mt-3 rounded-lg bg-muted/35 p-3">
          <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-muted-foreground"><ChevronRight className="size-3.5" />This course also requires</p>
          <RuleTree nodes={nestedNodes} depth={depth + 1} visitedCourseIds={nextVisited} onSelectCourse={onSelectCourse} />
        </div>
      ) : null}
    </div>
  )
}

/** Render standing, consent, placement, credit, and other non-course conditions. */
function ConditionRule({ node }: { node: PrerequisiteNodeOut }) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-amber-950">
      {node.node_type === "CONSENT" || node.node_type === "EXAM" || node.node_type === "OTHER" ? <ShieldQuestion className="mt-0.5 size-4 shrink-0" /> : <AlertCircle className="mt-0.5 size-4 shrink-0" />}
      <div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><span className="text-sm font-semibold">{conditionText(node)}</span><Badge className={requisiteBadgeClass(node.requisite_type)}>{requisiteLabel(node.requisite_type)}</Badge></div><p className="mt-1 text-xs text-amber-800">{conditionVerificationText(node)}</p></div>
    </div>
  )
}

/** Remove missing-course placeholders while retaining their available siblings. */
function visiblePrerequisiteNodes(nodes: PrerequisiteNodeOut[]): PrerequisiteNodeOut[] {
  return nodes.flatMap((node) => {
    if (isMissingCatalogCourse(node)) return []
    const children = visiblePrerequisiteNodes(node.children)
    if (node.node_type === "GROUP" && children.length === 0) return []
    return [{ ...node, children }]
  })
}

/** Identify catalog placeholders that the optimizer now treats as unavailable. */
function isMissingCatalogCourse(node: PrerequisiteNodeOut): boolean {
  return node.node_type === "OTHER" && Boolean(node.text_value?.startsWith("Referenced course not present in provided dataset:"))
}

/** Return readable instructions for a prerequisite group after filtering. */
function groupInstruction(node: PrerequisiteNodeOut, visibleCount: number): string {
  if (node.rule_operator === "ANY") return visibleCount === 1 ? "Complete this available course" : "Complete any one option"
  if (node.rule_operator === "N_OF") return `Complete ${Math.min(node.required_count ?? 1, visibleCount)} of these options`
  return "Complete all requirements"
}

/** Return a concise label for the timing semantics of a rule. */
function requisiteLabel(type: RequisiteType): string {
  if (type === "COREQUISITE") return "Co-requisite"
  if (type === "PRE_OR_COREQUISITE") return "Before or same term"
  if (type === "RECOMMENDED") return "Recommended"
  return "Prerequisite"
}

/** Return accessible colors for prerequisite timing labels. */
function requisiteBadgeClass(type: RequisiteType): string {
  if (type === "COREQUISITE" || type === "PRE_OR_COREQUISITE") return "bg-blue-100 text-blue-800"
  if (type === "RECOMMENDED") return "bg-slate-100 text-slate-700"
  return "bg-amber-100 text-amber-900"
}

/** Return the best structured description for a non-course rule leaf. */
function conditionText(node: PrerequisiteNodeOut): string {
  if (node.node_type === "STANDING") return `${titleCase(node.minimum_standing ?? "Required")} standing`
  if (node.node_type === "CREDIT_HOURS") return `${node.minimum_total_credits ?? 0} completed credit hours`
  if (node.node_type === "SUBJECT_LEVEL") return `${node.minimum_course_level ?? 0}-level subject preparation`
  if (node.node_type === "PROGRAM_MEMBERSHIP") return "Required program membership"
  return node.text_value || node.source_text || titleCase(node.node_type)
}

/** Explain whether the solver enforces or externally verifies a condition. */
function conditionVerificationText(node: PrerequisiteNodeOut): string {
  if (["STANDING", "CREDIT_HOURS", "SUBJECT_LEVEL", "PROGRAM_MEMBERSHIP"].includes(node.node_type)) return "Checked by the planning model using the student's scenario and scheduled progress."
  return "External condition: assumed satisfied during optimization and shown for advisor verification."
}

/** Convert enum-like uppercase text into a readable label. */
function titleCase(value: string): string {
  return value.toLowerCase().replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase())
}

/** Return alphabetized department filters available inside the selected college. */
function getDepartmentOptions(programs: ProgramOut[], collegeId: number | null): FilterOption[] {
  return Array.from(new Map(programs.filter((program) => collegeId === null || program.college_id === collegeId).map((program) => [program.department_id, program.department_name ?? program.department_code ?? "Department"]))).sort((a, b) => a[1].localeCompare(b[1]))
}
