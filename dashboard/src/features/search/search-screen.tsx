import { useMemo, useState } from "react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { formatRelative, typeLabel } from "@/lib/format"
import type { MemoryRecord } from "@/types"

export function SearchScreen({ memories, initialQuery = "", onOpenMemory }: { memories: MemoryRecord[]; initialQuery?: string; onOpenMemory: (memory: MemoryRecord) => void }) {
  const [query, setQuery] = useState(initialQuery)
  const [type, setType] = useState("all")
  const types = useMemo(() => ["all", ...Array.from(new Set(memories.map((memory) => memory.type))).slice(0, 5)], [memories])
  const results = useMemo(() => memories.filter((memory) => {
    if (type !== "all" && memory.type !== type) return false
    const needle = query.trim().toLowerCase()
    return !needle || `${memory.title} ${memory.body} ${memory.tags.join(" ")}`.toLowerCase().includes(needle)
  }), [memories, query, type])

  return (
    <section className="gam-scroll min-h-0 flex-1 overflow-y-auto">
      <div className="gam-column px-10 pb-28 pt-9 gam-fade-in">
        <Input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search memories…" className="h-auto rounded-none border-x-0 border-t-0 border-subtle bg-transparent px-0 pb-3 text-[17px] text-foreground shadow-none placeholder:text-faint focus-visible:ring-0" />
        <Tabs value={type} onValueChange={setType} className="mt-4">
          <TabsList variant="line" className="h-auto gap-5 p-0">
            {types.map((item) => <TabsTrigger key={item} value={item} className="h-auto rounded-none px-0 py-0 text-[13.5px] font-normal text-faint data-active:text-foreground after:bottom-[-8px] after:bg-foreground">{item === "all" ? "All" : typeLabel(item)}</TabsTrigger>)}
          </TabsList>
        </Tabs>
        <div className="mt-3">
          {results.map((memory) => <Button key={memory.id} variant="ghost" onClick={() => onOpenMemory(memory)} className="h-auto min-w-0 w-full flex-col items-start overflow-hidden whitespace-normal rounded-none border-x-0 border-t-0 border-b border-subtle px-0 py-[18px] text-left hover:bg-transparent"><span className="block w-full min-w-0 whitespace-normal break-words text-[15.5px] font-medium leading-[1.45] text-foreground">{memory.title}</span><span className="mt-1 block w-full whitespace-normal text-[13px] font-normal text-faint">{memory.type} · updated {formatRelative(memory.updated_at)} · confidence {memory.confidence.toFixed(2)}</span></Button>)}
          {results.length === 0 && <p className="py-10 text-sm text-faint">No memories match.</p>}
        </div>
      </div>
    </section>
  )
}
