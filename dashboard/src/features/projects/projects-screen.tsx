import { Check } from "@phosphor-icons/react"

import { Button } from "@/components/ui/button"
import type { DashboardData } from "@/types"

export function ProjectsScreen({ data, activeProject, onSelect }: { data: DashboardData; activeProject?: string; onSelect: (project: string) => void }) {
  return (
    <section className="gam-scroll min-h-0 flex-1 overflow-y-auto">
      <div className="gam-column px-5 pb-28 pt-9 gam-fade-in sm:px-10">
        <p className="mb-2.5 text-[12.5px] leading-relaxed text-faint">Everything your agents remember, grouped by project. Select one to make it active.</p>
        {data.projects.map((project) => {
          const memories = data.project_stats[project.name]?.memories ?? 0
          const candidates = data.project_stats[project.name]?.candidates ?? 0
          const current = project.name === activeProject
          return (
            <Button key={project.id} variant="ghost" onClick={() => onSelect(project.name)} className="h-auto min-w-0 w-full justify-start whitespace-normal rounded-none border-x-0 border-t-0 border-b border-subtle px-0 py-[19px] text-left hover:bg-transparent">
              <span className="min-w-0 flex-1">
                <span className="block text-base font-semibold text-foreground">{project.name}</span>
                <span className="mt-1 block text-[12.5px] font-normal text-faint">{memories} {memories === 1 ? "memory" : "memories"}{candidates ? ` · ${candidates} pending review` : ""}</span>
              </span>
              {current && <span className="flex items-center gap-1.5 text-[13px] font-normal text-faint"><Check size={13} />current</span>}
            </Button>
          )
        })}
        {data.projects.length === 0 && <p className="py-10 text-sm text-muted-foreground">No projects are registered yet.</p>}
      </div>
    </section>
  )
}
