import type { OptimizationObjectiveType } from "@/lib/types"

interface ObjectiveLabel {
  title: string
  description: string
}

export const OBJECTIVE_LABELS: Record<OptimizationObjectiveType, ObjectiveLabel> = {
  EARLIEST_GRADUATION: {
    title: "Graduate as soon as possible",
    description: "Finishes every requirement in the fewest possible terms.",
  },
  MIN_ADDITIONAL_CREDITS: {
    title: "Take the fewest extra credits",
    description: "Avoids padding your schedule with courses beyond what's required.",
  },
  MAX_REQUIREMENT_OVERLAP: {
    title: "Double-count courses where possible",
    description: "Prefers courses that satisfy more than one program's requirements at once.",
  },
  BALANCED_WORKLOAD: {
    title: "Keep terms evenly balanced",
    description: "Spreads credit hours evenly instead of some very heavy, some very light terms.",
  },
  MIN_SUMMER_ENROLLMENT: {
    title: "Avoid summer terms",
    description: "Only schedules a summer term when there's no other way to stay on track.",
  },
}
