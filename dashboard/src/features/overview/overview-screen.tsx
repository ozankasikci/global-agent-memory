import { Button } from "@/components/ui/button"
import { formatRelative, memoryExcerpt } from "@/lib/format"
import type { DashboardData, MemoryRecord } from "@/types"

interface OverviewScreenProps {
  data: DashboardData
  onReview: () => void
  onSearch: (query?: string) => void
  onOpenMemory: (memory: MemoryRecord) => void
}

export function OverviewScreen({ data, onReview, onOpenMemory }: OverviewScreenProps) {
  const active = data.memories.filter((memory) => memory.status === "active")
  const conventions = active.filter((memory) => memory.type === "convention")
  const decisions = active.filter((memory) => memory.type === "decision")
  const solutions = active.filter((memory) => memory.type === "solution")
  const preferences = active.filter((memory) => memory.type === "preference")

  return (
    <section className="gam-scroll min-h-0 flex-1 overflow-y-auto">
      <div className="gam-column px-5 pb-28 pt-11 gam-fade-in sm:px-10">
        <h1 className="mb-4 text-[27px] font-semibold tracking-[-0.015em] text-foreground">{data.selected_project ?? "Global memory"}</h1>
        {data.candidates.length > 0 ? <button type="button" onClick={onReview} className="flex w-full items-center gap-3 rounded-[10px] border border-[#2c2210] bg-[#141007] px-4 py-[13px] text-left"><span className="h-[7px] w-[7px] shrink-0 rounded-full bg-warning-foreground" /><span className="min-w-0 flex-1 text-sm text-[#d8c9a3]">{data.candidates.length} {data.candidates.length === 1 ? "candidate is" : "candidates are"} waiting for review.</span><span className="shrink-0 text-[13.5px] font-medium text-foreground">Review →</span></button> : <p className="m-0 text-[14.5px] text-muted-foreground">Your review queue is clear.</p>}

        <MemorySection title="Conventions" memories={conventions} onOpenMemory={onOpenMemory} />
        <MemorySection title="Decisions" memories={decisions} onOpenMemory={onOpenMemory} />

        {solutions.length > 0 && <section className="mt-[38px]"><SectionLabel>Known problems &amp; solutions</SectionLabel><div className="gam-panel rounded-xl border border-[#1f1f22] bg-card px-[18px] py-[3px]">{solutions.map((memory) => <Button key={memory.id} variant="ghost" onClick={() => onOpenMemory(memory)} className="h-auto min-w-0 w-full flex-col items-start overflow-hidden whitespace-normal rounded-none border-x-0 border-t-0 border-b border-[#17171b] px-0 py-[13px] text-left hover:bg-transparent"><span className="block w-full whitespace-normal break-words text-[14.5px] font-medium leading-relaxed text-[#e8e8ea]">{memory.title}</span><span className="mt-0.5 block w-full whitespace-normal break-words text-[13.5px] font-normal leading-relaxed text-[#8faf9a]">→ {memoryExcerpt(memory)}</span></Button>)}</div></section>}

        <MemorySection title="Preferences" memories={preferences} onOpenMemory={onOpenMemory} />

        {data.activity.length > 0 && <section className="mt-[38px]"><SectionLabel compact>Recent activity</SectionLabel>{data.activity.slice(0, 5).map((item, index) => <div key={`${item.created_at}-${index}`} className="flex gap-4 border-b border-subtle py-2.5 text-[13.5px]"><span className="flex-1 leading-relaxed text-muted-foreground">{item.actor} {item.action} “{item.target}”</span><span className="shrink-0 text-faint">{formatRelative(item.created_at)}</span></div>)}</section>}
      </div>
    </section>
  )
}

function MemorySection({ title, memories, onOpenMemory }: { title: string; memories: MemoryRecord[]; onOpenMemory: (memory: MemoryRecord) => void }) {
  if (memories.length === 0) return null
  return <section className="mt-[38px]"><SectionLabel>{title}</SectionLabel><div className="gam-panel rounded-xl border border-[#1f1f22] bg-card px-[18px] py-[3px]">{memories.map((memory) => <Button key={memory.id} variant="ghost" onClick={() => onOpenMemory(memory)} className="h-auto min-w-0 w-full justify-start overflow-hidden whitespace-normal rounded-none border-x-0 border-t-0 border-b border-[#17171b] px-0 py-3 text-left text-[15px] font-medium leading-relaxed text-[#e8e8ea] hover:bg-transparent hover:text-foreground"><span className="min-w-0 whitespace-normal break-words">{memory.title}</span></Button>)}</div></section>
}

function SectionLabel({ children, compact = false }: { children: React.ReactNode; compact?: boolean }) {
  return <div className={compact ? "mb-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-faint" : "mb-2.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-faint"}>{children}</div>
}
