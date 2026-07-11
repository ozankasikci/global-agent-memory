import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import type { DashboardData } from "@/types"

export function SystemScreen({ data, onReindex, onBackup }: { data: DashboardData; onReindex: () => Promise<void>; onBackup: () => Promise<void> }) {
  const stats = [
    [data.status.document_count, "indexed"],
    [data.status.pending_index_jobs, "indexing jobs"],
    [data.status.invalid_note_count, "invalid notes"],
  ]
  return (
    <section className="gam-scroll min-h-0 flex-1 overflow-y-auto">
      <div className="gam-column px-10 pb-28 pt-9 gam-fade-in">
        {data.services.map((service) => <div key={service.name} className="flex items-baseline border-b border-subtle py-[15px]"><div className="w-[200px] shrink-0 text-[15px] text-foreground">{service.name}</div><div className="flex-1 text-[13.5px] text-faint">{service.detail}</div><div className={cn("text-[13.5px]", service.state === "operational" ? "text-success" : service.state === "degraded" ? "text-warning" : "text-destructive")}>{service.state}</div></div>)}
        <div className="mt-[30px] flex gap-[38px]">{stats.map(([value, label]) => <div key={label}><div className="text-[22px] font-semibold text-foreground">{value}</div><div className="text-[13px] text-faint">{label}</div></div>)}</div>
        <div className="mt-9 flex gap-[22px]"><Button variant="link" onClick={() => void onReindex()} className="h-auto p-0 text-sm font-normal text-muted-foreground hover:text-foreground">Reindex vault</Button><Button variant="link" onClick={() => void onBackup()} className="h-auto p-0 text-sm font-normal text-muted-foreground hover:text-foreground">Back up now</Button></div>
      </div>
    </section>
  )
}
