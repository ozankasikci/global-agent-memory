import { useEffect, useMemo, useState } from "react"
import { ArrowLeft, ArrowRight, Check, FloppyDisk } from "@phosphor-icons/react"
import { toast } from "sonner"

import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"
import type { ClassificationUpdate, MemoryRecord, MemoryUpdate, MemoryVisibility } from "@/types"

interface CandidateDetailProps {
  candidate: MemoryRecord | null
  position: string
  onApprove: (candidate: MemoryRecord, classification: ClassificationUpdate) => Promise<MemoryRecord>
  onReject: (candidate: MemoryRecord, reason: string) => Promise<MemoryRecord>
  onUpdate: (candidate: MemoryRecord, patch: MemoryUpdate) => Promise<MemoryRecord>
  onOpenMemory: (id: string) => void
  onPrevious: () => void
  onNext: () => void
}

export function CandidateDetail({ candidate, position, onApprove, onReject, onUpdate, onOpenMemory, onPrevious, onNext }: CandidateDetailProps) {
  const [mode, setMode] = useState<"view" | "edit">("view")
  const [showRelated, setShowRelated] = useState(false)
  const [rejectOpen, setRejectOpen] = useState(false)
  const [approveOpen, setApproveOpen] = useState(false)
  const [approveVisibility, setApproveVisibility] = useState<MemoryVisibility>("standard")
  const [rejectReason, setRejectReason] = useState("Outdated")
  const [rejectNote, setRejectNote] = useState("")
  const [busy, setBusy] = useState(false)
  const [draft, setDraft] = useState<MemoryUpdate | null>(null)

  useEffect(() => {
    setMode("view")
    setShowRelated(false)
    setRejectOpen(false)
    setApproveOpen(false)
    setApproveVisibility("standard")
    setDraft(null)
  }, [candidate?.id])

  const paragraphs = useMemo(() => candidate?.body.split(/\n\s*\n/).filter((part) => !part.trim().startsWith("#")) ?? [], [candidate])
  const related = candidate?.possible_duplicates[0] ?? candidate?.conflicts[0]

  function startEdit() {
    if (!candidate) return
    setDraft({ title: candidate.title, body: candidate.body, tags: candidate.tags, confidence: candidate.confidence, importance: candidate.importance })
    setMode("edit")
  }

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null
      if (target?.matches("input, textarea, [contenteditable='true']") || !candidate || mode !== "view") return
      if (event.key.toLowerCase() === "e") {
        event.preventDefault()
        startEdit()
      } else if (event.key.toLowerCase() === "a") {
        event.preventDefault()
        openApproval()
      } else if (event.key.toLowerCase() === "r") {
        event.preventDefault()
        setRejectOpen(true)
      }
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [candidate, mode])

  async function run(action: () => Promise<unknown>) {
    setBusy(true)
    try {
      await action()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "The memory action failed.")
    } finally {
      setBusy(false)
    }
  }

  function openApproval() {
    setApproveVisibility("standard")
    setApproveOpen(true)
  }

  function approvalClassification(): ClassificationUpdate {
    if (approveVisibility === "protected") {
      return {
        visibility: "protected",
        access_policy: "user_approval",
        allowed_projects: candidate?.scope === "project" && candidate.project ? [candidate.project] : [],
        max_permission: "read",
      }
    }
    return {
      visibility: approveVisibility,
      access_policy: approveVisibility === "sealed" ? "per_access" : "user_approval",
      allowed_projects: [],
      max_permission: "read",
    }
  }

  if (!candidate) {
    return <section className="grid min-h-0 flex-1 place-items-center"><div className="text-center"><div className="mb-2 text-[17px] font-medium text-foreground">Nothing to review</div><div className="text-sm text-muted-foreground">New proposals from your agents will appear here.</div></div></section>
  }

  return (
    <section className="flex min-h-0 flex-1 flex-col">
      <div className="gam-scroll min-h-0 flex-1 overflow-y-auto">
        <div className="gam-column px-10 pb-28 pt-12 gam-fade-in">
          <div className="mb-[22px] text-[13px] text-faint">Candidate {position} · proposed by {candidate.source_kind} · {candidate.created_at ? new Date(candidate.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "recently"}</div>

          {mode === "view" ? <>
            <h1 className="mb-3.5 text-[26px] font-semibold leading-[1.3] tracking-[-0.01em] text-foreground">{candidate.title}</h1>
            <p className="mb-[30px] text-base leading-[1.65] text-muted-foreground">{candidate.summary}</p>
            {(paragraphs.length ? paragraphs : [candidate.body]).map((paragraph, index) => <p key={index} className="mb-4 whitespace-pre-wrap text-[15px] leading-7 text-body">{paragraph}</p>)}

            <div className="mt-[34px] border-l-2 border-border pl-4">
              <div className="mb-1.5 text-xs text-faint">Evidence</div>
              <p className="m-0 text-sm leading-[1.65] text-muted-foreground">{candidate.evidence ?? "No explicit evidence was captured with this proposal."}</p>
            </div>

            <div className="mt-[30px] text-[13px] text-faint">{candidate.type} · {candidate.scope} · confidence {candidate.confidence.toFixed(2)} · importance {candidate.importance.toFixed(2)}</div>

            {related && <div className="mt-[22px] text-sm leading-relaxed text-warning-foreground">{candidate.conflicts.length ? "Contradicts an existing memory." : `Similar to an existing memory (${Math.round((related.similarity ?? 0) * 100)}% match).`} <button type="button" onClick={() => setShowRelated((value) => !value)} className="text-warning underline underline-offset-4">{showRelated ? "Hide comparison" : "Compare"}</button></div>}
            {related && showRelated && <button type="button" onClick={() => onOpenMemory(related.id)} className="mt-4 block w-full rounded-[10px] border border-subtle bg-card px-5 py-[18px] text-left"><div className="mb-2 text-xs text-faint">Existing memory · {related.status}</div><div className="mb-1.5 text-[14.5px] font-medium text-foreground">{related.title}</div><p className="m-0 text-sm leading-relaxed text-muted-foreground">{related.excerpt}</p></button>}
          </> : draft && <EditForm draft={draft} onChange={setDraft} />}
        </div>
      </div>

      <div className="shrink-0 border-t border-subtle bg-background">
        <div className="gam-column flex items-center gap-[22px] px-10 py-4">
          {mode === "view" ? <>
            <Button disabled={busy} onClick={openApproval} className="h-9 bg-foreground px-[22px] font-semibold text-background hover:bg-foreground/90"><Check weight="bold" />Approve</Button>
            <Button disabled={busy} variant="link" onClick={startEdit} className="h-auto p-0 font-normal text-muted-foreground hover:text-foreground">Edit</Button>
            <Button disabled={busy} variant="link" onClick={() => setRejectOpen(true)} className="h-auto p-0 font-normal text-muted-foreground hover:text-foreground">Reject</Button>
            <div className="ml-auto flex gap-[18px]">
              <Button variant="link" onClick={onPrevious} className="h-auto p-0 text-[13px] font-normal text-faint hover:text-muted-foreground"><ArrowLeft />prev</Button>
              <Button variant="link" onClick={onNext} className="h-auto p-0 text-[13px] font-normal text-faint hover:text-muted-foreground">next<ArrowRight /></Button>
            </div>
          </> : <>
            <Button disabled={busy || !draft} onClick={() => void run(async () => { if (!draft) return; await onUpdate(candidate, draft); openApproval() })} className="h-9 bg-foreground px-[22px] font-semibold text-background hover:bg-foreground/90"><FloppyDisk />Save & approve</Button>
            <Button variant="link" onClick={() => setMode("view")} className="h-auto p-0 font-normal text-muted-foreground">Cancel</Button>
          </>}
        </div>
      </div>

      <AlertDialog open={rejectOpen} onOpenChange={setRejectOpen}>
        <AlertDialogContent>
          <AlertDialogHeader><AlertDialogTitle>Reject this candidate?</AlertDialogTitle><AlertDialogDescription>The reason is kept with the lifecycle event so future agents understand the decision.</AlertDialogDescription></AlertDialogHeader>
          <div className="flex flex-wrap gap-2">{["Outdated", "Duplicate", "Incorrect", "Too specific", "Low confidence"].map((reason) => <Button key={reason} size="sm" variant={rejectReason === reason ? "secondary" : "outline"} onClick={() => setRejectReason(reason)}>{reason}</Button>)}</div>
          <Textarea value={rejectNote} onChange={(event) => setRejectNote(event.target.value)} placeholder="Optional note…" />
          <AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction onClick={() => void run(() => onReject(candidate, `${rejectReason}${rejectNote ? ` — ${rejectNote}` : ""}`))}>Reject candidate</AlertDialogAction></AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <Dialog open={approveOpen} onOpenChange={setApproveOpen}>
        <DialogContent className="max-w-[520px] gap-0 rounded-[14px] border-border bg-[#0d0d10] p-0 sm:max-w-[520px]" showCloseButton={false}>
          <div className="px-7 pb-[26px] pt-6">
            <DialogHeader className="gap-0">
              <span className="mb-1.5 text-[13px] text-faint">Approve memory</span>
              <DialogTitle className="text-[19px] font-semibold leading-[1.35] tracking-[-0.01em]">{candidate.title}</DialogTitle>
              <DialogDescription className="mb-[18px] mt-1 text-[13.5px] leading-5">Choose how visible this memory is to agents before it&apos;s saved.</DialogDescription>
            </DialogHeader>
            <div className="space-y-[9px]">
              {approvalVisibilityOptions.map((option) => (
                <button key={option.value} type="button" onClick={() => setApproveVisibility(option.value)} className={cn("w-full rounded-[10px] border px-[15px] py-3 text-left outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring/40", approveVisibility === option.value ? "border-foreground" : "border-border hover:border-faint")}>
                  <span className="block text-[14.5px] font-medium text-foreground">{option.label}</span>
                  <span className="mt-1 block text-[12.5px] leading-5 text-muted-foreground">{option.description}</span>
                </button>
              ))}
            </div>
            {approveVisibility !== "standard" && <p className="mt-3 text-[12.5px] leading-5 text-warning-foreground">Protected and sealed are for sensitive knowledge—never store credentials, passwords, or API keys.</p>}
            <DialogFooter className="mx-0 mb-0 mt-[22px] flex-row justify-start gap-5 rounded-none border-0 bg-transparent p-0">
              <Button disabled={busy} onClick={() => void run(async () => { await onApprove(candidate, approvalClassification()); setApproveOpen(false) })} className="h-10 px-[26px]">Approve</Button>
              <Button variant="link" disabled={busy} onClick={() => setApproveOpen(false)} className="h-auto p-0 font-normal text-muted-foreground">Cancel</Button>
            </DialogFooter>
          </div>
        </DialogContent>
      </Dialog>
    </section>
  )
}

const approvalVisibilityOptions: Array<{ value: MemoryVisibility; label: string; description: string }> = [
  { value: "standard", label: "Standard", description: "Agents can read it automatically in ordinary search." },
  { value: "protected", label: "Protected", description: "Excluded from agent search; access needs your approval." },
  { value: "sealed", label: "Sealed", description: "Hidden until you unlock; every access is confirmed." },
]

export function EditForm({ draft, onChange }: { draft: MemoryUpdate; onChange: (next: MemoryUpdate) => void }) {
  return <div className="space-y-4"><Input value={draft.title} onChange={(event) => onChange({ ...draft, title: event.target.value })} className="h-auto rounded-none border-x-0 border-t-0 border-subtle bg-transparent px-0 pb-2 text-2xl font-semibold text-foreground shadow-none focus-visible:ring-0" /><Textarea value={draft.body} onChange={(event) => onChange({ ...draft, body: event.target.value })} className="min-h-[280px] resize-y border-subtle bg-card text-[15px] leading-7" /><div className="grid grid-cols-2 gap-3"><Input type="number" min="0" max="1" step="0.05" value={draft.confidence} onChange={(event) => onChange({ ...draft, confidence: Number(event.target.value) })} /><Input type="number" min="0" max="1" step="0.05" value={draft.importance} onChange={(event) => onChange({ ...draft, importance: Number(event.target.value) })} /></div></div>
}
