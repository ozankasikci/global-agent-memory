import { useEffect, useState } from "react"
import { ArrowLeft, FloppyDisk, LockKey } from "@phosphor-icons/react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { EditForm } from "@/features/review/candidate-detail"
import { ClassificationDialog } from "@/features/memory/classification-dialog"
import { formatRelative } from "@/lib/format"
import type { ClassificationUpdate, MemoryRecord, MemoryUpdate, ProjectRecord } from "@/types"

interface MemoryDetailProps {
  memory: MemoryRecord
  onBack: () => void
  onArchive: (memory: MemoryRecord, reason: string) => Promise<MemoryRecord>
  onOpenObsidian: (memory: MemoryRecord) => Promise<void>
  onOpenFile: (memory: MemoryRecord) => Promise<void>
  onUpdate: (memory: MemoryRecord, patch: MemoryUpdate) => Promise<MemoryRecord>
  onClassify: (memory: MemoryRecord, classification: ClassificationUpdate) => Promise<MemoryRecord>
  onUnlock: (memory: MemoryRecord, purpose: string) => Promise<MemoryRecord>
  projects: ProjectRecord[]
}

export function MemoryDetail({ memory, projects, onBack, onArchive, onOpenFile, onUpdate, onClassify, onUnlock }: MemoryDetailProps) {
  const [editing, setEditing] = useState(false)
  const [classifying, setClassifying] = useState(false)
  const [busy, setBusy] = useState(false)
  const [revealed, setRevealed] = useState<MemoryRecord | null>(null)
  const [draft, setDraft] = useState<MemoryUpdate>(() => toDraft(memory))

  useEffect(() => { setDraft(toDraft(memory)); setRevealed(null) }, [memory])
  const displayed = revealed ?? memory

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
      <div className="gam-column px-5 pb-28 pt-9 gam-fade-in sm:px-10">
        <Button variant="link" onClick={onBack} className="mb-[26px] h-auto p-0 text-[13px] font-normal text-faint hover:text-muted-foreground"><ArrowLeft />All memories</Button>
        <h1 className="mb-3 flex items-center gap-2 text-[26px] font-semibold leading-[1.3] tracking-[-0.01em] text-foreground">{displayed.visibility === "sealed" && <LockKey size={20} className="text-faint" />}{displayed.visibility === "sealed" && !revealed ? "Sealed memory" : displayed.title}</h1>
        <div className="mb-3.5 text-[12.5px] text-faint">{displayed.visibility === "sealed" && !revealed ? "Sealed · title, summary, and path are hidden" : `${displayed.type} · updated ${formatRelative(displayed.updated_at)} · confidence ${displayed.confidence.toFixed(2)}`}</div>

        {displayed.visibility === "sealed" && !revealed ? <div className="mb-10"><p className="mb-0 mt-6 max-w-lg text-[15px] leading-[1.7] text-muted-foreground">This memory is sealed. Its content stays hidden until you unlock it, and every access is confirmed and recorded. Sealed memories must never hold credentials, passwords, or API keys.</p><Button className="mt-7" onClick={() => { setBusy(true); void onUnlock(memory, "Owner review from memory detail").then(setRevealed).catch((error) => toast.error(error instanceof Error ? error.message : "Unlock failed")).finally(() => setBusy(false)) }} disabled={busy}>Unlock to view</Button></div> : <>
        <div className="mb-3.5 flex items-baseline gap-2.5 border-b border-subtle pb-5 pt-2.5"><span className="min-w-0 flex-1 text-[13px] leading-5 text-muted-foreground">{visibilityDescription(displayed)}</span><Button variant="link" onClick={() => setClassifying(true)} className="h-auto shrink-0 p-0 text-[13px] font-normal text-foreground">Change visibility</Button></div>
        {revealed && displayed.visibility === "sealed" && <div className="mb-4 text-[12.5px] text-warning-foreground">Unlocked for this view · this access is recorded</div>}
        <div className="mb-[30px] whitespace-pre-wrap text-[15px] leading-7 text-body">{displayed.body}</div>

        <div className="mb-[34px] border-l-2 border-border pl-4">
          <div className="mb-1.5 text-xs text-faint">Evidence</div>
          <p className="mb-1.5 text-sm leading-[1.65] text-muted-foreground">{displayed.evidence ?? "No explicit evidence section was captured."}</p>
          <div className="text-[12.5px] text-faint">{displayed.source_ref ?? displayed.source_kind}</div>
        </div>

        <div className="mb-2.5 text-xs text-faint">History</div>
        <div className="flex gap-3 py-1 text-[13.5px]"><span className="w-[86px] shrink-0 text-faint">{formatRelative(displayed.updated_at)}</span><span className="text-muted-foreground">Last updated</span></div>
        <div className="flex gap-3 py-1 text-[13.5px]"><span className="w-[86px] shrink-0 text-faint">{formatRelative(displayed.created_at)}</span><span className="text-muted-foreground">Created by {displayed.source_kind}</span></div>
        </>}

        <div className="mt-[38px] flex gap-[22px]">
          {displayed.visibility !== "sealed" && <Button variant="link" onClick={() => { setDraft(toDraft(displayed)); setEditing(true) }} className="h-auto p-0 text-sm font-normal text-muted-foreground hover:text-foreground">Edit</Button>}
          <Button variant="link" onClick={() => setClassifying(true)} className="h-auto p-0 text-sm font-normal text-muted-foreground hover:text-foreground">Change visibility</Button>
          <Button variant="link" onClick={() => void onArchive(memory, "Archived from dashboard")} className="h-auto p-0 text-sm font-normal text-muted-foreground hover:text-foreground">Archive</Button>
          {displayed.visibility !== "sealed" && <Button variant="link" onClick={() => void onOpenFile(displayed)} className="h-auto p-0 text-sm font-normal text-muted-foreground hover:text-foreground">Open Markdown file</Button>}
        </div>
      </div>

      <Dialog open={editing} onOpenChange={setEditing}><DialogContent className="max-h-[88vh] overflow-y-auto"><DialogHeader><DialogTitle>Edit memory</DialogTitle><DialogDescription>Changes are written to the canonical Markdown note.</DialogDescription></DialogHeader><EditForm draft={draft} onChange={setDraft} /><DialogFooter><Button variant="ghost" onClick={() => setEditing(false)}>Cancel</Button><Button disabled={busy} onClick={() => void save()}><FloppyDisk />Save changes</Button></DialogFooter></DialogContent></Dialog>
      <ClassificationDialog memory={memory} projects={projects} open={classifying} onOpenChange={setClassifying} onSave={(value) => onClassify(memory, value)} />
    </section>
  )
}

function toDraft(memory: MemoryRecord): MemoryUpdate {
  return { title: memory.title, body: memory.body, tags: memory.tags, confidence: memory.confidence, importance: memory.importance }
}

function visibilityDescription(memory: MemoryRecord) {
  if (memory.visibility === "protected") return "Protected — excluded from agent retrieval; access needs your approval"
  if (memory.visibility === "sealed") return "Sealed — hidden until unlocked; confirmation required for every access"
  return "Standard — included in ordinary agent search and context"
}
