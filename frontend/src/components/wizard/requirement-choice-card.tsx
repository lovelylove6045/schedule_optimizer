import { useState } from "react"
import { Ban, Check, CheckCircle2, ChevronDown, ChevronUp, ListPlus, Loader2, RotateCcw, TriangleAlert } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { useCourseGroupCoursesQuery } from "@/hooks/use-requirement-choices"
import {
  type PrerequisiteClause,
  unmetPrerequisiteClauses,
  useCoursePrerequisitesQuery,
} from "@/hooks/use-course-prerequisites"
import type { CourseOut, RequirementChoiceOut } from "@/lib/types"
import { cn } from "@/lib/utils"

/** How many options to render before collapsing behind "Show all". Keeps a
 * 40-option elective pool from burying the next choice off-screen. */
const VISIBLE_OPTION_LIMIT = 6

interface RequirementChoiceCardProps {
  choice: RequirementChoiceOut
  selectedCourseIds: number[]
  excludedCourseIds: number[]
  /** Every course the student has already completed or picked anywhere in the
   * wizard so far, used to decide whether an option's prerequisites still need
   * planning for -- not just against this one choice's own selection. */
  satisfiedCourseIds: number[]
  onToggle: (courseId: number, maxSelections: number) => void
  onToggleExclude: (courseId: number) => void
  onClear: () => void
}

/** One elective decision point: the requirement, its options, and which the
 * student picked or ruled out. Anything left neither picked nor excluded is
 * left to the optimizer. */
export function RequirementChoiceCard({
  choice,
  selectedCourseIds,
  excludedCourseIds,
  satisfiedCourseIds,
  onToggle,
  onToggleExclude,
  onClear,
}: RequirementChoiceCardProps) {
  const [showAll, setShowAll] = useState(false)
  const [search, setSearch] = useState("")
  const fullGroupQuery = useCourseGroupCoursesQuery(choice.course_group_id, showAll && choice.options_truncated)
  const options = fullGroupQuery.data?.courses ?? choice.options
  const filtered = filterCourses(options, search)
  const visible = showAll ? filtered : filtered.slice(0, VISIBLE_OPTION_LIMIT)
  const maxSelections = maxSelectionsFor(choice)
  const excludedHere = options.filter((course) => excludedCourseIds.includes(course.course_id))
  return (
    <div className="glass-inset space-y-3 rounded-xl p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-semibold">{choice.label}</p>
          <p className="text-xs text-muted-foreground">
            {choice.program_name} · {choice.requirement_set_name}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          {choice.already_satisfied ? (
            <Badge className="bg-success text-success-foreground">
              <CheckCircle2 className="size-3" aria-hidden="true" />
              Already done
            </Badge>
          ) : null}
          <Badge variant="secondary" className="font-mono text-[0.7rem]">
            {requirementSummary(choice)}
          </Badge>
          {selectedCourseIds.length > 0 ? (
            <Button variant="ghost" size="icon-xs" aria-label="Clear this choice" onClick={onClear}>
              <RotateCcw className="size-3.5" />
            </Button>
          ) : null}
        </div>
      </div>
      {choice.options_truncated && !showAll ? (
        <p className="text-xs text-muted-foreground">
          Showing {Math.min(VISIBLE_OPTION_LIMIT, choice.options.length)} of {choice.total_option_count} approved
          courses.
        </p>
      ) : null}
      {showAll && options.length > VISIBLE_OPTION_LIMIT ? (
        <Input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Filter these courses…"
          aria-label={`Filter courses for ${choice.label}`}
        />
      ) : null}
      {fullGroupQuery.isPending && showAll && choice.options_truncated ? (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
          Loading all {choice.total_option_count} options…
        </p>
      ) : null}
      <ul className="grid gap-2 sm:grid-cols-2">
        {visible.map((course) => (
          <li key={course.course_id}>
            <CourseOption
              course={course}
              isSelected={selectedCourseIds.includes(course.course_id)}
              isExcluded={excludedCourseIds.includes(course.course_id)}
              satisfiedCourseIds={satisfiedCourseIds}
              onSelect={() => onToggle(course.course_id, maxSelections)}
              onToggleExclude={() => onToggleExclude(course.course_id)}
            />
          </li>
        ))}
      </ul>
      {filtered.length === 0 ? (
        <p className="text-xs text-muted-foreground">No courses match "{search}".</p>
      ) : null}
      {canExpand(choice, filtered.length) ? (
        <Button variant="ghost" size="sm" onClick={() => setShowAll(!showAll)}>
          {showAll ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}
          {showAll ? "Show fewer" : `Show all ${expandableCount(choice, filtered.length)} options`}
        </Button>
      ) : null}
      {selectedCourseIds.length === 0 ? (
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <ListPlus className="size-3.5" aria-hidden="true" />
          No preference — the optimizer will choose for you.
        </p>
      ) : null}
      {excludedHere.length > 0 ? (
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Ban className="size-3.5 text-destructive" aria-hidden="true" />
          {excludedHere.length} course{excludedHere.length === 1 ? "" : "s"} excluded here — the optimizer won't
          assign {excludedHere.length === 1 ? "it" : "them"} to you.
        </p>
      ) : null}
    </div>
  )
}

/** One selectable course chip inside a choice, with a separate small control for
 * ruling it out entirely (e.g. "I'm weak at this subject, don't put me in it"),
 * and a warning when the course still has an unmet prerequisite -- informational
 * only, since the optimizer (not this screen) decides term placement and can
 * often just schedule the prerequisite first on its own. */
function CourseOption({
  course,
  isSelected,
  isExcluded,
  satisfiedCourseIds,
  onSelect,
  onToggleExclude,
}: {
  course: CourseOut
  isSelected: boolean
  isExcluded: boolean
  satisfiedCourseIds: number[]
  onSelect: () => void
  onToggleExclude: () => void
}) {
  const courseLabel = `${course.subject_code} ${course.course_number}`
  const unmetClauses = useUnmetPrerequisiteClauses(course.course_id, satisfiedCourseIds)
  return (
    <div
      className={cn(
        "glass-raised flex w-full items-start gap-1.5 rounded-lg p-2.5 text-left transition-colors",
        isSelected ? "border-gold ring-2 ring-gold/35" : isExcluded ? "border-destructive/40 opacity-60" : "",
      )}
    >
      <button
        type="button"
        onClick={onSelect}
        disabled={isExcluded}
        aria-pressed={isSelected}
        className={cn(
          "flex flex-1 items-start gap-2.5 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed",
          !isSelected && !isExcluded && "hover:opacity-80",
        )}
      >
        <span
          className={cn(
            "mt-0.5 flex size-4 shrink-0 items-center justify-center rounded-full border",
            isSelected ? "border-gold bg-gold text-gold-foreground" : "border-muted-foreground/40",
          )}
        >
          {isSelected ? <Check className="size-2.5" aria-hidden="true" /> : null}
        </span>
        <span className="min-w-0 flex-1">
          <span className={cn("block font-mono text-xs font-semibold", isExcluded && "line-through")}>
            {courseLabel}
          </span>
          <span className="block truncate text-xs text-muted-foreground">{course.course_title}</span>
          {unmetClauses.length > 0 ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="mt-1 flex w-fit items-start gap-1 text-[0.7rem] text-amber-600 dark:text-amber-400">
                  <TriangleAlert className="mt-0.5 size-3 shrink-0" aria-hidden="true" />
                  <span className="underline decoration-dotted decoration-from-font">
                    Also needs: {describeClauses(unmetClauses)}
                  </span>
                </span>
              </TooltipTrigger>
              <TooltipContent>
                Not a blocker — the planner will try to schedule these for you automatically. This is just a
                heads-up so you know they're still outstanding.
              </TooltipContent>
            </Tooltip>
          ) : null}
        </span>
        <span className="shrink-0 font-mono text-[0.7rem] text-muted-foreground">{course.credit_hours} cr</span>
      </button>
      <button
        type="button"
        onClick={onToggleExclude}
        aria-pressed={isExcluded}
        aria-label={isExcluded ? `Stop excluding ${courseLabel}` : `Exclude ${courseLabel} (I'm weak in this)`}
        title={isExcluded ? "Excluded — click to allow again" : "Exclude this course"}
        className={cn(
          "mt-0.5 shrink-0 rounded-md p-1 text-muted-foreground/60 outline-none transition-colors hover:text-destructive focus-visible:ring-2 focus-visible:ring-ring",
          isExcluded && "text-destructive",
        )}
      >
        <Ban className="size-3.5" aria-hidden="true" />
      </button>
    </div>
  )
}

/** This option's prerequisite clauses that aren't already covered by completed
 * or picked-elsewhere coursework -- what the student would still need to plan
 * for if they picked it. Empty (not an error) while the tree is still loading. */
function useUnmetPrerequisiteClauses(courseId: number, satisfiedCourseIds: number[]): PrerequisiteClause[] {
  const prerequisitesQuery = useCoursePrerequisitesQuery(courseId)
  return unmetPrerequisiteClauses(prerequisitesQuery.data ?? [], satisfiedCourseIds)
}

/** How many clauses, and how many options within an "any one of" clause, to
 * name before falling back to "and N more" -- a 60-course elective pool
 * should read as one manageable line, not a wall of course codes. */
const MAX_CLAUSES_SHOWN = 3
const MAX_CLAUSE_OPTIONS_SHOWN = 3

/** Render a list of unmet prerequisite clauses as one short, readable phrase. */
function describeClauses(clauses: PrerequisiteClause[]): string {
  const shown = clauses.slice(0, MAX_CLAUSES_SHOWN).map(describeClause)
  const remaining = clauses.length - shown.length
  const suffix = remaining > 0 ? `, and ${remaining} more requirement${remaining === 1 ? "" : "s"}` : ""
  return shown.join("; ") + suffix
}

/** Render one clause: a bare course code when it's just one course, or
 * "one of A, B, C (+N more)" when any one of several would do. */
function describeClause(clause: PrerequisiteClause): string {
  const codes = clause.options.map((course) => `${course.subject_code} ${course.course_number}`)
  if (codes.length === 1) return codes[0]
  const shown = codes.slice(0, MAX_CLAUSE_OPTIONS_SHOWN)
  const remaining = codes.length - shown.length
  return remaining > 0
    ? `one of ${shown.join(", ")} (+${remaining} more)`
    : `one of ${shown.join(" or ")}`
}

/** Describe what the requirement asks for, in credit hours when that's how it's stated. */
function requirementSummary(choice: RequirementChoiceOut): string {
  if (choice.required_credit_hours) return `${choice.required_credit_hours} cr needed`
  if (choice.choose_count > 1) return `pick ${choice.choose_count}`
  return "pick 1"
}

/** How many courses the student may pick here. Credit-hour requirements have no
 * fixed course count, so allow enough picks to plausibly cover the target
 * (3 credits is the standard course size) without capping them at one. */
function maxSelectionsFor(choice: RequirementChoiceOut): number {
  if (choice.required_credit_hours) {
    return Math.max(choice.choose_count, Math.ceil(choice.required_credit_hours / 3))
  }
  return choice.choose_count
}

/** Case-insensitive filter over a choice's options by code or title. */
function filterCourses(courses: CourseOut[], search: string): CourseOut[] {
  const trimmed = search.trim().toLowerCase()
  if (!trimmed) return courses
  return courses.filter((course) =>
    `${course.subject_code} ${course.course_number} ${course.course_title}`.toLowerCase().includes(trimmed),
  )
}

/** Whether there's anything left to reveal (more filtered options, or a truncated
 * server-side list we haven't fetched yet). */
function canExpand(choice: RequirementChoiceOut, filteredCount: number): boolean {
  return filteredCount > VISIBLE_OPTION_LIMIT || choice.options_truncated
}

/** The option count to advertise on the expand button. */
function expandableCount(choice: RequirementChoiceOut, filteredCount: number): number {
  return choice.options_truncated ? choice.total_option_count : filteredCount
}
