import { useEffect, useState } from "react"
import { ArrowLeft, FloppyDisk } from "@phosphor-icons/react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { EditForm } from "@/features/review/candidate-detail"
import { formatRelative } from "@/lib/format"
import type { MemoryRecord, MemoryUpdate } from "@/types"

interface MemoryDetailProps {
  memory: MemoryRecord
  onBack: () => void
  onArchive: (memory: MemoryRecord, reason: string) => Promise<MemoryRecord>
  onOpenObsidian: (memory: MemoryRecord) => Promise<void>
  onOpenFile: (memory: MemoryRecord) => Promise<void>
  onUpdate: (memory: MemoryRecord, patch: MemoryUpdate) => Promise<MemoryRecord>
}

export function MemoryDetail({ memory, onBack, onArchive, onOpenFile, onUpdate }: MemoryDetailProps) {
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [draft, setDraft] = useState<MemoryUpdate>(() => toDraft(memory))

  useEffect(() => setDraft(toDraft(memory)), [memory])

  async function save() {
    setBusy(true)
    try {
      await onUpdate(memory, draft)
      setEditing(false)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "The memory could not be updated.")
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="gam-scroll min-h-0 flex-1 overflow-y-auto">
      <div className="gam-column px-10 pb-28 pt-9 gam-fade-in">
        <Button variant="link" onClick={onBack} className="mb-[26px] h-auto p-0 text-[13px] font-normal text-faint hover:text-muted-foreground"><ArrowLeft />All memories</Button>
        <h1 className="mb-3 text-2xl font-semibold leading-[1.3] tracking-[-0.01em] text-foreground">{memory.title}</h1>
        <div className="mb-7 text-[13px] text-faint">{memory.type} · updated {formatRelative(memory.updated_at)} · confidence {memory.confidence.toFixed(2)}</div>
        <div className="mb-[30px] whitespace-pre-wrap text-[15px] leading-7 text-body">{memory.body}</div>

        <div className="mb-[34px] border-l-2 border-border pl-4">
          <div className="mb-1.5 text-xs text-faint">Evidence</div>
          <p className="mb-1.5 text-sm leading-[1.65] text-muted-foreground">{memory.evidence ?? "No explicit evidence section was captured."}</p>
          <div className="text-[12.5px] text-faint">{memory.source_ref ?? memory.source_kind}</div>
        </div>

        <div className="mb-2.5 text-xs text-faint">History</div>
        <div className="flex gap-3 py-1 text-[13.5px]"><span className="w-[86px] shrink-0 text-faint">{formatRelative(memory.updated_at)}</span><span className="text-muted-foreground">Last updated</span></div>
        <div className="flex gap-3 py-1 text-[13.5px]"><span className="w-[86px] shrink-0 text-faint">{formatRelative(memory.created_at)}</span><span className="text-muted-foreground">Created by {memory.source_kind}</span></div>

        <div className="mt-[38px] flex gap-[22px]">
          <Button variant="link" onClick={() => { setDraft(toDraft(memory)); setEditing(true) }} className="h-auto p-0 text-sm font-normal text-muted-foreground hover:text-foreground">Edit</Button>
          <Button variant="link" onClick={() => void onArchive(memory, "Archived from dashboard")} className="h-auto p-0 text-sm font-normal text-muted-foreground hover:text-foreground">Archive</Button>
          <Button variant="link" onClick={() => void onOpenFile(memory)} className="h-auto p-0 text-sm font-normal text-muted-foreground hover:text-foreground">Open Markdown file</Button>
        </div>
      </div>

      <Dialog open={editing} onOpenChange={setEditing}><DialogContent className="max-h-[88vh] overflow-y-auto"><DialogHeader><DialogTitle>Edit memory</DialogTitle><DialogDescription>Changes are written to the canonical Markdown note.</DialogDescription></DialogHeader><EditForm draft={draft} onChange={setDraft} /><DialogFooter><Button variant="ghost" onClick={() => setEditing(false)}>Cancel</Button><Button disabled={busy} onClick={() => void save()}><FloppyDisk />Save changes</Button></DialogFooter></DialogContent></Dialog>
    </section>
  )
}

function toDraft(memory: MemoryRecord): MemoryUpdate {
  return { title: memory.title, body: memory.body, tags: memory.tags, confidence: memory.confidence, importance: memory.importance }
}
