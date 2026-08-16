import { BookMarked } from "lucide-react"

/** Display the single authoritative catalog snapshot used by this prototype. */
export function CatalogSnapshotNotice() {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-primary/20 bg-primary/5 px-3 py-2 text-xs text-muted-foreground">
      <BookMarked className="size-4 shrink-0 text-primary" aria-hidden="true" />
      <span>
        <strong className="font-semibold text-foreground">Prototype catalog:</strong> Missouri S&amp;T FA26 / 2026
        catalog snapshot.
      </span>
    </div>
  )
}
