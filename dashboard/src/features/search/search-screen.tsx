import { useMemo, useState } from "react"
import { LockKey, ShieldCheck } from "@phosphor-icons/react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { formatRelative, typeLabel } from "@/lib/format"
import { durationLabel, permissionLabel } from "@/features/access/access-policy"
import type { AccessGrantRecord, MemoryRecord } from "@/types"

export function SearchScreen({ memories, grants = [], initialQuery = "", onOpenMemory }: { memories: MemoryRecord[]; grants?: AccessGrantRecord[]; initialQuery?: string; onOpenMemory: (memory: MemoryRecord) => void }) {
  const [query, setQuery] = useState(initialQuery)
  const [type, setType] = useState("all")
  const [agentView, setAgentView] = useState(false)
  const types = ["all", "standard", "protected", "sealed", "grants"]
  const results = useMemo(() => memories.filter((memory) => {
    if (memory.status !== "active") return false
    if (agentView && memory.visibility !== "standard") return false
    if (type === "grants") return false
    if (type !== "all" && memory.visibility !== type) return false
    const needle = query.trim().toLowerCase()
    if (memory.visibility === "sealed") return !needle && (type === "all" || type === "sealed")
    return !needle || `${memory.title} ${memory.body} ${memory.tags.join(" ")}`.toLowerCase().includes(needle)
  }), [agentView, memories, query, type])
  const hiddenCount = useMemo(() => memories.filter((memory) => memory.status === "active" && memory.visibility !== "standard").length, [memories])
  const visibleGrants = grants.filter((grant) => grant.status === "active")

  return (
    <section className="gam-scroll min-h-0 flex-1 overflow-y-auto">
      <div className="gam-column px-5 pb-28 pt-9 gam-fade-in sm:px-10">
        <div className="flex items-end gap-5 border-b border-border pb-0"><Input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search memories…" className="h-auto min-w-0 flex-1 rounded-none border-0 bg-transparent px-0 pb-3 text-[17px] text-foreground shadow-none placeholder:text-faint focus-visible:ring-0" /><Button aria-label={agentView ? "Owner view" : "Agent view"} variant="link" onClick={() => { setAgentView((value) => !value); setType("all") }} className="mb-3 h-auto shrink-0 p-0 text-[12.5px] font-normal text-faint hover:text-foreground">{agentView ? "Viewing as agent" : "View as agent"}</Button></div>
        <Tabs value={type} onValueChange={setType} className="mt-4">
          <TabsList variant="line" className="h-auto flex-wrap gap-[18px] p-0">
            {types.filter((item) => !agentView || item === "all" || item === "standard").map((item) => <TabsTrigger key={item} value={item} className="h-auto rounded-none px-0 py-0 text-[13.5px] font-normal text-faint data-active:text-foreground after:hidden">{item === "all" ? "All" : item === "grants" ? "Active grants" : typeLabel(item)}</TabsTrigger>)}
          </TabsList>
        </Tabs>
        {agentView && <p className="mb-1.5 mt-4 text-[12.5px] leading-5 text-faint">This is what an agent sees. Protected and sealed memories never expose titles, excerpts, tags, or paths.</p>}
        <div className="mt-1">
          {type !== "grants" && results.map((memory) => <Button key={memory.id} variant="ghost" onClick={() => onOpenMemory(memory)} className="h-auto min-w-0 w-full items-start justify-between overflow-hidden whitespace-normal rounded-none border-x-0 border-t-0 border-b border-subtle px-0 py-[18px] text-left hover:bg-transparent"><span className="min-w-0 flex-1"><span className="flex w-full min-w-0 items-center gap-2 whitespace-normal break-words text-base font-semibold leading-[1.4] text-foreground">{memory.visibility === "protected" && <ShieldCheck className="shrink-0 text-warning-foreground" size={15} />}{memory.visibility === "sealed" && <LockKey className="shrink-0 text-faint" size={15} />}{memory.visibility === "sealed" ? "Sealed memory" : memory.title}</span><span className="mt-1 block w-full whitespace-normal text-[12.5px] font-normal text-faint">{memory.project ?? "No project · global"} · {memory.visibility === "sealed" ? "locked · unlock to view" : `${memory.type} · updated ${formatRelative(memory.updated_at)}${memory.visibility === "standard" ? ` · confidence ${memory.confidence.toFixed(2)}` : ""}`}</span></span>{memory.visibility !== "standard" && <span className={memory.visibility === "protected" ? "ml-3 shrink-0 text-xs font-normal text-warning-foreground" : "ml-3 shrink-0 text-xs font-normal text-faint"}>{memory.visibility}</span>}</Button>)}
          {type === "grants" && visibleGrants.map((grant) => <div key={grant.id} className="border-b border-subtle py-[17px]"><div className="flex items-baseline gap-3"><div className="min-w-0 flex-1 text-[15.5px] font-semibold text-foreground">{grant.agent}</div><div className="shrink-0 text-[12.5px] text-faint">{permissionLabel(grant.permission)} · {durationLabel(grant.duration)}</div></div><div className="mt-1 text-[12.5px] text-faint">{grant.scope_count} protected {grant.scope_count === 1 ? "memory" : "memories"} · {grant.purpose}</div></div>)}
          {agentView && hiddenCount > 0 && <div className="mt-[18px] rounded-[10px] border border-border bg-[#0d0d10] px-[18px] py-4"><div className="text-[14.5px] leading-[1.55] text-card-foreground">Protected memory may be relevant. User approval is required.</div><div className="mt-1 text-[12.5px] leading-5 text-faint">The agent receives only this neutral signal—no identifying metadata—and can submit an access request.</div></div>}
          {type !== "grants" && results.length === 0 && !agentView && <p className="py-10 text-sm text-faint">No memories match.</p>}
          {type === "grants" && visibleGrants.length === 0 && <p className="py-10 text-sm leading-6 text-faint">No active grants. When you approve an agent request, it appears here.</p>}
        </div>
      </div>
    </section>
  )
}
