import { BookOpen } from "lucide-react"
import { CatalogProgramDetail } from "@/components/catalog/catalog-program-detail"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import type { ProgramOut } from "@/lib/types"

interface CatalogProgramDialogProps {
  program: ProgramOut | undefined
  open: boolean
  onOpenChange: (open: boolean) => void
}

/** Show one program's complete catalog record in a roomy, focused dialog. */
export function CatalogProgramDialog({ program, open, onOpenChange }: CatalogProgramDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="h-[min(54rem,calc(100svh-2rem))] w-[min(72rem,calc(100vw-2rem))] max-w-none grid-rows-[auto_minmax(0,1fr)] gap-0 overflow-hidden p-0 sm:max-w-none">
        <DialogHeader className="shrink-0 border-b bg-background/35 px-6 py-5 pr-14 text-left">
          <div className="flex items-center gap-3">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <BookOpen className="size-5" aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <DialogTitle className="text-xl">Program details</DialogTitle>
              <DialogDescription className="mt-1">
                Review catalog information, credit hours, and the complete requirement structure.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>
        <div className="scrollbar-slim min-h-0 flex-1 overflow-x-hidden overflow-y-auto px-4 py-5 sm:px-6">
          <CatalogProgramDetail program={program} />
        </div>
      </DialogContent>
    </Dialog>
  )
}
