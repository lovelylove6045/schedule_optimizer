import { useState } from "react"
import { Plus } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import type { StudentCreditIn } from "@/lib/types"

interface TransferCreditFormProps {
  onAdd: (credit: StudentCreditIn) => void
}

/** A small manual-entry form for transfer credit that has no catalog course match. */
export function TransferCreditForm({ onAdd }: TransferCreditFormProps) {
  const [title, setTitle] = useState("")
  const [credits, setCredits] = useState("")
  const canAdd = title.trim().length > 0 && Number(credits) > 0
  /** Report the entered transfer credit to the parent and clear the form. */
  function handleAdd() {
    if (!canAdd) return
    onAdd({
      source_type: "TRANSFER",
      status: "COMPLETED",
      external_course_title: title.trim(),
      credits_earned: Number(credits),
    })
    setTitle("")
    setCredits("")
  }
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-dashed p-4 sm:flex-row sm:items-end">
      <div className="flex-1 space-y-1.5">
        <Label htmlFor="transfer-title">Transfer course title</Label>
        <Input
          id="transfer-title"
          placeholder="e.g. Intro to Programming (Community College)"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
        />
      </div>
      <div className="w-full space-y-1.5 sm:w-32">
        <Label htmlFor="transfer-credits">Credit hours</Label>
        <Input
          id="transfer-credits"
          type="number"
          min="0"
          step="0.5"
          value={credits}
          onChange={(event) => setCredits(event.target.value)}
        />
      </div>
      <Button type="button" variant="secondary" disabled={!canAdd} onClick={handleAdd}>
        <Plus className="size-4" />
        Add transfer credit
      </Button>
    </div>
  )
}
