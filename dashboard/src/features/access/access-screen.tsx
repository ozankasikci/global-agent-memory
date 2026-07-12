import { useEffect, useMemo, useState } from "react"
import { Check, X } from "@phosphor-icons/react"

import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import {
  approvalSummary,
  durationAllowed,
  durationLabel,
  durations,
  highestAllowedPermission,
  permissionAllowed,
  permissionLabel,
  permissions,
  type AccessDuration,
} from "@/features/access/access-policy"
import { formatRelative } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { AccessApproval, AccessRequestRecord, AccessState, MemoryPermission } from "@/types"

export function AccessScreen({
  access,
  onApprove,
  onDeny,
  onRevoke,
}: {
  access: AccessState
  onApprove: (id: string, approval: AccessApproval) => Promise<void>
  onDeny: (id: string, reason: string) => Promise<void>
  onRevoke: (id: string) => Promise<void>
}) {
  const [selected, setSelected] = useState<AccessRequestRecord | null>(null)
  const pending = access.requests.filter((request) => request.status === "pending")
  const active = access.grants.filter((grant) => grant.status === "active")
  const stale = access.grants.filter((grant) => grant.status !== "active")

  return (
    <section className="gam-scroll min-h-0 flex-1 overflow-y-auto">
      <div className="gam-column px-10 pb-28 pt-9 gam-fade-in">
        <div className="mb-10">
          <h1 className="text-[22px] font-semibold tracking-[-0.02em]">Access</h1>
          <p className="mt-2 text-[13px] leading-5 text-faint">Agents can request protected memory. Only you can approve access.</p>
        </div>

        <SectionLabel>Pending requests</SectionLabel>
        <div className="mb-11 border-t border-subtle">
          {pending.map((request) => (
            <button key={request.id} type="button" onClick={() => setSelected(request)} className="group flex w-full items-start justify-between gap-5 border-b border-subtle py-[18px] text-left">
              <div className="min-w-0">
                <div className="text-[15px] font-medium text-foreground">{request.agent}</div>
                <div className="mt-1 text-[13px] leading-5 text-muted-foreground">{request.purpose}</div>
                <div className="mt-1 text-[12.5px] text-faint">{request.project ?? "Shared memory"} · requested {permissionLabel(request.permission)} for {durationLabel(request.requested_duration).toLowerCase()} · {formatRelative(request.created_at)}</div>
              </div>
              <span className="mt-0.5 shrink-0 text-[13px] text-muted-foreground group-hover:text-foreground">Review →</span>
            </button>
          ))}
          {!pending.length && <EmptyRow>No requests are waiting.</EmptyRow>}
        </div>

        <SectionLabel>Active grants</SectionLabel>
        <div className="mb-11 border-t border-subtle">
          {active.map((grant) => (
            <div key={grant.id} className="flex items-start justify-between gap-5 border-b border-subtle py-[18px]">
              <div>
                <div className="text-[14.5px] font-medium">{grant.agent} · {permissionLabel(grant.permission)}</div>
                <div className="mt-1 text-[13px] text-muted-foreground">{grant.purpose}</div>
                <div className="mt-1 text-[12.5px] text-faint">{grant.scope_count} protected {grant.scope_count === 1 ? "memory" : "memories"} · {durationLabel(grant.duration)}</div>
              </div>
              <Button variant="link" onClick={() => void onRevoke(grant.id)} className="h-auto shrink-0 p-0 text-[13px] font-normal text-faint hover:text-foreground">Revoke</Button>
            </div>
          ))}
          {!active.length && <EmptyRow>No active grants.</EmptyRow>}
        </div>

        {!!stale.length && <><SectionLabel>Expired and revoked</SectionLabel><div className="mb-11 border-t border-subtle">{stale.slice(0, 8).map((grant) => <div key={grant.id} className="flex justify-between gap-4 border-b border-subtle py-3.5 text-[13px]"><span className="text-muted-foreground">{grant.agent} · {grant.purpose}</span><span className="shrink-0 text-faint">{grant.status}</span></div>)}</div></>}

        <SectionLabel>Access history</SectionLabel>
        <div className="border-t border-subtle">
          {access.events.slice(0, 20).map((event) => <div key={event.id} className="grid grid-cols-[82px_1fr_auto] gap-3 border-b border-subtle py-3.5 text-[12.5px]"><span className="text-faint">{formatRelative(event.created_at)}</span><span className="text-muted-foreground">{event.agent} {event.action} · {event.purpose}</span><span className="text-faint">{event.status}</span></div>)}
          {!access.events.length && <EmptyRow>No access activity yet.</EmptyRow>}
        </div>
      </div>
      <RequestDialog request={selected} onClose={() => setSelected(null)} onApprove={onApprove} onDeny={onDeny} />
    </section>
  )
}

export function RequestDialog({
  request,
  onClose,
  onApprove,
  onDeny,
}: {
  request: AccessRequestRecord | null
  onClose: () => void
  onApprove: (id: string, approval: AccessApproval) => Promise<void>
  onDeny: (id: string, reason: string) => Promise<void>
}) {
  const [permission, setPermission] = useState<MemoryPermission>(request?.permission ?? "read")
  const [duration, setDuration] = useState<AccessDuration>(request?.requested_duration ?? "once")
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const selectedMatches = useMemo(
    () => request?.matches.filter((match) => selectedIds.includes(match.id)) ?? [],
    [request, selectedIds],
  )

  useEffect(() => {
    setPermission(request?.permission ?? "read")
    setDuration(request?.requested_duration ?? "once")
    setSelectedIds([])
  }, [request?.id, request?.permission, request?.requested_duration])

  useEffect(() => {
    if (!request) return
    if (!permissionAllowed(permission, request.permission, selectedMatches)) {
      setPermission(highestAllowedPermission(request.permission, selectedMatches))
    }
    if (!durationAllowed(duration, request.requested_duration, selectedMatches)) setDuration("once")
  }, [duration, permission, request, selectedMatches])

  if (!request) return null
  const currentRequest = request
  const canAllow = selectedIds.length > 0
    && permissionAllowed(permission, request.permission, selectedMatches)
    && durationAllowed(duration, request.requested_duration, selectedMatches)

  function toggleMemory(id: string, checked: boolean) {
    setSelectedIds((current) => checked ? [...current, id] : current.filter((item) => item !== id))
  }

  function permissionUnavailableReason(item: MemoryPermission) {
    if (permissionAllowed(item, currentRequest.permission, [])) {
      const limitingMatch = selectedMatches.find((match) => !permissionAllowed(item, currentRequest.permission, [match]))
      if (limitingMatch) return `Limited by “${limitingMatch.title}” (max ${permissionLabel(limitingMatch.max_permission).toLowerCase()}).`
    }
    return `The agent only requested ${permissionLabel(currentRequest.permission).toLowerCase()} access.`
  }

  function durationUnavailableReason(item: AccessDuration) {
    const perAccess = selectedMatches.find((match) => match.access_policy === "per_access")
    if (perAccess && item !== "once") return `“${perAccess.title}” requires approval for every retrieval.`
    return "Longer than the agent requested."
  }

  async function act(action: "allow" | "deny") {
    setBusy(true)
    try {
      if (action === "allow") await onApprove(currentRequest.id, { permission, duration, memory_ids: selectedIds })
      else await onDeny(currentRequest.id, "Denied by owner")
      onClose()
    } finally { setBusy(false) }
  }

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose() }}>
      <DialogContent className="gam-scroll top-[52px] max-h-[calc(100vh-104px)] max-w-[600px] translate-y-0 gap-0 overflow-y-auto rounded-[14px] border border-border bg-[#0d0d10] p-0 shadow-[0_30px_70px_-24px_rgba(0,0,0,0.75)] sm:max-w-[600px]" showCloseButton={false}>
        <div className="px-6 pb-7 pt-6 sm:px-[30px] sm:pb-[30px]">
        <DialogHeader className="gap-0">
          <div className="mb-[18px] flex items-center justify-between">
            <span className="text-[13px] text-warning-foreground">Human approval required</span>
            <Button type="button" variant="ghost" size="icon-sm" onClick={onClose} aria-label="Close access request" className="-mr-1 text-faint hover:bg-transparent hover:text-foreground"><X /></Button>
          </div>
          <DialogTitle className="mb-5 pr-8 text-[22px] font-semibold leading-[1.3] tracking-[-0.01em]">{request.agent} is requesting protected memory</DialogTitle>
          <DialogDescription className="sr-only">Review the request and choose the exact permission, duration, and protected memories covered by the grant.</DialogDescription>
        </DialogHeader>

        <dl className="border-t border-subtle text-sm">
          <RequestFact label="Project">{request.project ?? "Shared"}</RequestFact>
          <RequestFact label="Purpose">{request.purpose}</RequestFact>
          <RequestFact label="Requested permission">{permissionLabel(request.permission)}</RequestFact>
          <RequestFact label="Requested duration">{durationLabel(request.requested_duration)}</RequestFact>
          <RequestFact label="Protected matches">{request.matched_count}</RequestFact>
          <RequestFact label="Sealed matches">{request.sealed_match_count} · metadata hidden</RequestFact>
        </dl>

        <fieldset className="mt-[30px]">
          <legend className="text-xs font-medium uppercase tracking-[0.07em] text-faint">Access level</legend>
          <p className="mb-3 mt-1.5 text-[13px] leading-5 text-faint">Grant the least that does the job. You can lower the agent&apos;s request, never raise it.</p>
          <div className="space-y-[9px]">
            {permissions.map((item) => {
              const allowed = permissionAllowed(item, request.permission, selectedMatches)
              const isSelected = permission === item
              return <button key={item} type="button" aria-label={permissionLabel(item)} disabled={!allowed} onClick={() => setPermission(item)} className={cn("w-full rounded-[10px] border px-4 py-3 text-left outline-none transition-colors focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/40", isSelected ? "border-foreground bg-transparent" : "border-border hover:border-faint", !allowed && "cursor-not-allowed border-subtle opacity-100 hover:border-subtle")}>
                <span className="flex items-baseline gap-2.5"><span className={cn("text-[14.5px] font-medium", allowed ? "text-foreground" : "text-faint/70")}>{permissionLabel(item)}</span>{isSelected && allowed && <span className="text-xs text-success">selected</span>}</span>
                <span className={cn("mt-1 block text-[12.5px] leading-5", allowed ? "text-muted-foreground" : "text-faint/60")}>{permissionDescription(item)}</span>
                {!allowed && <span className="mt-1.5 block text-xs leading-[1.45] text-warning-foreground/75">Unavailable — {permissionUnavailableReason(item)}</span>}
              </button>
            })}
          </div>
        </fieldset>

        <fieldset className="mt-[26px]">
          <legend className="mb-3 text-xs font-medium uppercase tracking-[0.07em] text-faint">Duration</legend>
          <div className="flex flex-wrap gap-2.5">
            {durations.map((item) => {
              const allowed = durationAllowed(item, request.requested_duration, selectedMatches)
              return <button key={item} type="button" aria-label={durationLabel(item)} disabled={!allowed} onClick={() => setDuration(item)} className={cn("min-h-10 max-w-[190px] rounded-[9px] border px-[13px] py-2 text-left text-[13.5px] font-medium outline-none transition-colors focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/40", duration === item && allowed ? "border-foreground text-foreground" : "border-border text-muted-foreground hover:border-faint", !allowed && "cursor-not-allowed border-subtle text-faint/60 hover:border-subtle")}>
                <span className="block">{durationLabel(item)}</span>
                {!allowed && <span className="mt-1 block text-[11px] font-normal leading-[1.35] text-faint/70">{durationUnavailableReason(item)}</span>}
              </button>
            })}
          </div>
        </fieldset>

        <fieldset className="mt-[30px]">
          <legend className="text-xs font-medium uppercase tracking-[0.07em] text-faint">Exact memory scope</legend>
          <p className="mb-3 mt-1.5 text-[13px] leading-5 text-faint">Select the memories this grant covers. Nothing is selected by default.</p>
          <div className="gam-scroll max-h-[230px] overflow-y-auto border-y border-subtle">
            {request.matches.map((match) => (
              <label key={match.id} className={cn("flex gap-3 border-b border-subtle py-3 last:border-b-0", !match.eligible && "cursor-not-allowed")}>
                <Checkbox aria-label={`Select ${match.title}`} checked={selectedIds.includes(match.id)} disabled={!match.eligible} onCheckedChange={(checked) => toggleMemory(match.id, checked === true)} className="mt-0.5" />
                <span className="min-w-0 flex-1">
                  <span className={cn("block text-[13.5px] font-medium", match.eligible ? "text-foreground" : "text-faint")}>{match.title}</span>
                  <span className="mt-0.5 block text-[12px] leading-5 text-faint">{match.type} · {match.project ?? "Shared"} · max {permissionLabel(match.max_permission).toLowerCase()} · {match.access_policy === "per_access" ? "ask every retrieval" : "temporary grants"}</span>
                  {!match.eligible && <span className="mt-1 block text-xs text-warning-foreground/75">No longer eligible — policy changed since the request</span>}
                </span>
              </label>
            ))}
            {!request.matches.length && <div className="py-5 text-[13px] text-faint">No protected matches are currently eligible.</div>}
          </div>
          {!!request.sealed_match_count && <p className="mt-3 text-[12.5px] leading-5 text-faint">{request.sealed_match_count} sealed {request.sealed_match_count === 1 ? "match" : "matches"} — metadata stays hidden and each retrieval needs its own owner unlock.</p>}
        </fieldset>

        <div aria-live="polite" className="mt-6 rounded-[10px] border border-border bg-[#0d0d10] px-4 py-3.5 text-[14px] leading-6 text-muted-foreground">
          {selectedIds.length ? `${approvalSummary(permission, duration, selectedIds.length)}.` : "Select at least one eligible memory to approve."}
        </div>

        <DialogFooter className="mx-0 mb-0 mt-[18px] flex-row items-center justify-start gap-[22px] rounded-none border-0 bg-transparent p-0">
          <Button disabled={busy || !canAllow} onClick={() => void act("allow")} className="h-10 px-[26px]"><Check />Allow</Button>
          <Button variant="link" disabled={busy} onClick={() => void act("deny")} className="h-auto p-0 font-normal text-destructive hover:text-destructive/80"><X />Deny</Button>
          <span className="ml-auto hidden text-[12.5px] text-faint/70 sm:inline">Agents can request, never approve.</span>
        </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function RequestFact({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="grid grid-cols-[130px_1fr] gap-4 border-b border-subtle py-[11px] sm:grid-cols-[160px_1fr]"><dt className="text-faint">{label}</dt><dd className="min-w-0 leading-5 text-body">{children}</dd></div>
}

function permissionDescription(permission: MemoryPermission) {
  return {
    read: "View and retrieve memory",
    edit: "Read, plus update memory content",
    manage: "Edit, plus archive, supersede, and lifecycle operations",
  }[permission]
}

function SectionLabel({ children }: { children: React.ReactNode }) { return <div className="mb-2.5 text-[11px] font-medium uppercase tracking-[0.12em] text-faint">{children}</div> }
function EmptyRow({ children }: { children: React.ReactNode }) { return <div className="border-b border-subtle py-[18px] text-[13px] text-faint">{children}</div> }
