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
      <div className="gam-column px-10 pb-28 pt-11 gam-fade-in">
        <h1 className="mb-2 text-2xl font-semibold tracking-[-0.01em] text-foreground">{data.selected_project ?? "Global memory"}</h1>
        {data.candidates.length > 0 ? <p className="m-0 text-[14.5px] text-muted-foreground">{data.candidates.length} {data.candidates.length === 1 ? "candidate is" : "candidates are"} waiting for review. <Button variant="link" onClick={onReview} className="h-auto p-0 text-[14.5px] font-normal text-foreground underline underline-offset-4">Review →</Button></p> : <p className="m-0 text-[14.5px] text-muted-foreground">Your review queue is clear.</p>}

        <MemorySection title="Conventions" memories={conventions} onOpenMemory={onOpenMemory} />
        <MemorySection title="Decisions" memories={decisions} onOpenMemory={onOpenMemory} />

        {solutions.length > 0 && <section className="mt-[38px]"><SectionLabel>Known problems & solutions</SectionLabel>{solutions.map((memory) => <Button key={memory.id} variant="ghost" onClick={() => onOpenMemory(memory)} className="h-auto min-w-0 w-full flex-col items-start overflow-hidden whitespace-normal rounded-none border-x-0 border-t-0 border-b border-subtle px-0 py-3 text-left hover:bg-transparent"><span className="block w-full whitespace-normal break-words text-[14.5px] font-normal leading-relaxed text-body">{memory.title}</span><span className="mt-0.5 block w-full whitespace-normal break-words text-sm font-normal leading-relaxed text-faint">→ {memoryExcerpt(memory)}</span></Button>)}</section>}

        <MemorySection title="Preferences" memories={preferences} onOpenMemory={onOpenMemory} />

        {data.activity.length > 0 && <section className="mt-[38px]"><SectionLabel>Recent activity</SectionLabel>{data.activity.slice(0, 5).map((item, index) => <div key={`${item.created_at}-${index}`} className="flex gap-4 border-b border-subtle py-2.5 text-sm"><span className="flex-1 leading-relaxed text-muted-foreground">{item.actor} {item.action} “{item.target}”</span><span className="shrink-0 text-faint">{formatRelative(item.created_at)}</span></div>)}</section>}
      </div>
    </section>
  )
}

function MemorySection({ title, memories, onOpenMemory }: { title: string; memories: MemoryRecord[]; onOpenMemory: (memory: MemoryRecord) => void }) {
  if (memories.length === 0) return null
  return <section className="mt-[38px]"><SectionLabel>{title}</SectionLabel>{memories.map((memory) => <Button key={memory.id} variant="ghost" onClick={() => onOpenMemory(memory)} className="h-auto min-w-0 w-full justify-start overflow-hidden whitespace-normal rounded-none border-x-0 border-t-0 border-b border-subtle px-0 py-[11px] text-left text-[15px] font-normal leading-relaxed text-body hover:bg-transparent hover:text-foreground"><span className="min-w-0 whitespace-normal break-words">{memory.title}</span></Button>)}</section>
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return <div className="mb-1.5 text-xs uppercase tracking-[0.07em] text-faint">{children}</div>
}
