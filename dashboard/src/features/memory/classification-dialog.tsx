import { useEffect, useState } from "react"
import { LockKey, LockOpen, ShieldCheck } from "@phosphor-icons/react"

import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { permissionLabel, permissions } from "@/features/access/access-policy"
import { cn } from "@/lib/utils"
import type { ClassificationUpdate, MemoryPermission, MemoryRecord, MemoryVisibility, ProjectRecord } from "@/types"

const visibilityOptions: Array<{ value: MemoryVisibility; title: string; description: string; icon: typeof LockOpen }> = [
  { value: "standard", title: "Standard", description: "Available to agents through normal memory search.", icon: LockOpen },
  { value: "protected", title: "Protected", description: "Agents see only a neutral relevance signal until you approve.", icon: ShieldCheck },
  { value: "sealed", title: "Sealed", description: "Never returned to agents. Owner unlock is one view and audited.", icon: LockKey },
]

export function ClassificationDialog({
  memory,
  projects,
  open,
  onOpenChange,
  onSave,
}: {
  memory: MemoryRecord
  projects: ProjectRecord[]
  open: boolean
  onOpenChange: (open: boolean) => void
  onSave: (value: ClassificationUpdate) => Promise<MemoryRecord>
}) {
  const [visibility, setVisibility] = useState<MemoryVisibility>(memory.visibility)
  const [accessPolicy, setAccessPolicy] = useState<"user_approval" | "per_access">(memory.access_policy)
  const [maxPermission, setMaxPermission] = useState<MemoryPermission>(memory.max_permission)
  const [allowedProjects, setAllowedProjects] = useState<string[]>(memory.allowed_projects)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setVisibility(memory.visibility)
    setAccessPolicy(memory.access_policy)
    setMaxPermission(memory.max_permission)
    setAllowedProjects(memory.scope === "project" && memory.project ? [memory.project] : memory.allowed_projects)
  }, [memory])

  function toggleProject(name: string, checked: boolean) {
    setAllowedProjects((current) => checked ? [...current, name] : current.filter((project) => project !== name))
  }

  async function save() {
    setBusy(true)
    try {
      const classification: ClassificationUpdate = visibility === "protected"
        ? {
          visibility,
          access_policy: accessPolicy,
          allowed_projects: memory.scope === "project" && memory.project ? [memory.project] : allowedProjects,
          max_permission: maxPermission,
        }
        : {
          visibility,
          access_policy: visibility === "sealed" ? "per_access" : "user_approval",
          allowed_projects: [],
          max_permission: "read",
        }
      await onSave(classification)
      onOpenChange(false)
    } finally { setBusy(false) }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[88vh] max-w-[560px] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Change visibility</DialogTitle>
          <DialogDescription>Classification controls every agent-facing retrieval path.</DialogDescription>
        </DialogHeader>

        <div className="space-y-2">
          {visibilityOptions.map((option) => {
            const Icon = option.icon
            return <button key={option.value} type="button" onClick={() => setVisibility(option.value)} className={cn("flex w-full gap-3 rounded-md border p-4 text-left transition-colors", visibility === option.value ? "border-foreground/30 bg-muted" : "border-border hover:bg-muted/50")}><Icon className="mt-0.5 shrink-0" size={18} /><span><span className="block text-sm font-medium">{option.title}</span><span className="mt-1 block text-[12.5px] leading-5 text-muted-foreground">{option.description}</span></span></button>
          })}
        </div>

        {visibility === "protected" && (
          <div className="space-y-5 border-t border-subtle pt-4">
            <fieldset>
              <legend className="mb-2 text-xs text-faint">Maximum permission</legend>
              <div className="grid grid-cols-3 gap-2">
                {permissions.map((permission) => <Button key={permission} type="button" variant={maxPermission === permission ? "secondary" : "outline"} onClick={() => setMaxPermission(permission)} className="justify-start"><ShieldCheck />{permissionLabel(permission)}</Button>)}
              </div>
              <p className="mt-2 text-[12px] leading-5 text-faint">An owner may approve this level or a lower one. Agents can never elevate it.</p>
            </fieldset>

            <fieldset>
              <legend className="mb-2 text-xs text-faint">Approval policy</legend>
              <div className="grid grid-cols-2 gap-2">
                <Button type="button" variant={accessPolicy === "user_approval" ? "secondary" : "outline"} onClick={() => setAccessPolicy("user_approval")} className="h-auto justify-start py-2.5 text-left"><span><span className="block">Temporary grants</span><span className="mt-0.5 block text-[11px] font-normal text-faint">One retrieval, timed, task, or session</span></span></Button>
                <Button type="button" variant={accessPolicy === "per_access" ? "secondary" : "outline"} onClick={() => setAccessPolicy("per_access")} className="h-auto justify-start py-2.5 text-left"><span><span className="block">Ask every retrieval</span><span className="mt-0.5 block text-[11px] font-normal text-faint">Only one-retrieval grants</span></span></Button>
              </div>
            </fieldset>

            <fieldset>
              <legend className="mb-1 text-xs text-faint">Allowed projects</legend>
              {memory.scope === "project" ? (
                <div className="rounded-md border border-subtle px-3 py-2 text-[13px] text-muted-foreground">Locked to {memory.project}</div>
              ) : (
                <>
                  <p className="mb-2 text-[12px] leading-5 text-faint">Select projects to restrict access. Nothing selected means all configured projects.</p>
                  <div className="max-h-[180px] overflow-y-auto border-y border-subtle">
                    {projects.map((project) => <label key={project.id} className="flex items-center gap-3 border-b border-subtle py-2.5 last:border-b-0"><Checkbox aria-label={`Allow ${project.name}`} checked={allowedProjects.includes(project.name)} onCheckedChange={(checked) => toggleProject(project.name, checked === true)} /><span className="text-[13px] text-muted-foreground">{project.name}</span></label>)}
                    {!projects.length && <div className="py-4 text-[12.5px] text-faint">No projects are configured.</div>}
                  </div>
                </>
              )}
            </fieldset>
          </div>
        )}

        <p className="text-[12px] leading-5 text-warning-foreground">Do not store passwords, credentials, or API keys in memory—even when sealed.</p>
        <DialogFooter><Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button><Button disabled={busy} onClick={() => void save()}>Save classification</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
