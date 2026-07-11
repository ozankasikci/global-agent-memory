import { useEffect, useMemo, useState } from "react"
import { ArrowClockwise, Database, WarningCircle } from "@phosphor-icons/react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import { MemoryDetail } from "@/features/memory/memory-detail"
import { OverviewScreen } from "@/features/overview/overview-screen"
import { ProjectsScreen } from "@/features/projects/projects-screen"
import { CandidateDetail } from "@/features/review/candidate-detail"
import { SearchScreen } from "@/features/search/search-screen"
import { SystemScreen } from "@/features/system/system-screen"
import { useDashboard } from "@/hooks/use-dashboard"
import { cn } from "@/lib/utils"
import type { MemoryRecord, Screen } from "@/types"

const navigation: Array<{ screen: Screen; label: string }> = [
  { screen: "overview", label: "Overview" },
  { screen: "review", label: "Review" },
  { screen: "search", label: "Memories" },
  { screen: "projects", label: "Projects" },
  { screen: "system", label: "System" },
]

export function App() {
  const dashboard = useDashboard()
  const [screen, setScreen] = useState<Screen>("overview")
  const [selectedId, setSelectedId] = useState<string>()
  const [detailId, setDetailId] = useState<string>()
  const [searchQuery, setSearchQuery] = useState("")

  const selected = useMemo(() => dashboard.data?.candidates.find((candidate) => candidate.id === selectedId) ?? dashboard.data?.candidates[0] ?? null, [dashboard.data?.candidates, selectedId])
  const detail = useMemo(() => dashboard.data?.memories.find((memory) => memory.id === detailId), [dashboard.data?.memories, detailId])

  useEffect(() => {
    if (!selectedId && dashboard.data?.candidates[0]) setSelectedId(dashboard.data.candidates[0].id)
    if (selectedId && !dashboard.data?.candidates.some((candidate) => candidate.id === selectedId)) {
      setSelectedId(dashboard.data?.candidates[0]?.id)
    }
  }, [dashboard.data?.candidates, selectedId])

  function moveCandidate(direction: number) {
    const candidates = dashboard.data?.candidates ?? []
    if (!candidates.length) return
    const index = Math.max(0, candidates.findIndex((candidate) => candidate.id === selected?.id))
    setSelectedId(candidates[(index + direction + candidates.length) % candidates.length].id)
  }

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null
      if (target?.matches("input, textarea, [contenteditable='true']") || screen !== "review" || !dashboard.data) return
      if (event.key === "ArrowRight" || event.key.toLowerCase() === "j") {
        event.preventDefault()
        moveCandidate(1)
      } else if (event.key === "ArrowLeft" || event.key.toLowerCase() === "k") {
        event.preventDefault()
        moveCandidate(-1)
      } else if (event.key.toLowerCase() === "a" && selected) {
        event.preventDefault()
        void dashboard.approve(selected).catch(showError)
      }
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [dashboard, screen, selected])

  function openMemory(memoryOrId: MemoryRecord | string) {
    const id = typeof memoryOrId === "string" ? memoryOrId : memoryOrId.id
    setDetailId(id)
    setScreen("detail")
  }

  if (dashboard.loading) return <LoadingState />
  if (dashboard.error || !dashboard.data) return <ErrorState message={dashboard.error ?? "No dashboard data was returned."} onRetry={dashboard.reload} />

  const data = dashboard.data
  const position = selected ? `${data.candidates.findIndex((candidate) => candidate.id === selected.id) + 1} of ${data.candidates.length}` : "—"

  function navigate(next: Screen) {
    setScreen(next)
    if (next !== "search") setSearchQuery("")
  }

  return (
    <TooltipProvider>
      <div className="flex h-dvh min-h-[680px] min-w-[900px] flex-col overflow-hidden bg-background text-foreground">
        <header className="gam-header flex h-[66px] shrink-0 items-center gap-7 px-10">
          <button type="button" onClick={() => navigate("overview")} className="mr-auto text-sm font-semibold text-foreground">Global Agent Memory</button>
          <nav className="flex items-center gap-1">
            {navigation.map((item) => {
              const active = screen === item.screen || (item.screen === "search" && screen === "detail")
              const label = item.screen === "review" && data.candidates.length ? `${item.label} · ${data.candidates.length}` : item.label
              return <Button key={item.screen} variant="ghost" size="sm" onClick={() => navigate(item.screen)} className={cn("h-8 rounded-md px-2.5 text-[13px] font-normal text-muted-foreground hover:bg-transparent hover:text-foreground", active && "text-foreground underline decoration-border underline-offset-[7px]")}>{label}</Button>
            })}
          </nav>
        </header>

        <main className="flex min-h-0 flex-1 flex-col">
          {screen === "review" && <CandidateDetail candidate={selected} position={position} onApprove={dashboard.approve} onReject={dashboard.reject} onUpdate={dashboard.update} onOpenMemory={openMemory} onPrevious={() => moveCandidate(-1)} onNext={() => moveCandidate(1)} />}
          {screen === "overview" && <OverviewScreen data={data} onReview={() => navigate("review")} onSearch={(query) => { setSearchQuery(query ?? ""); setScreen("search") }} onOpenMemory={openMemory} />}
          {screen === "search" && <SearchScreen memories={data.memories} initialQuery={searchQuery} onOpenMemory={openMemory} />}
          {screen === "projects" && <ProjectsScreen data={data} activeProject={dashboard.project} onSelect={(project) => { dashboard.selectProject(project); setScreen("overview") }} />}
          {screen === "system" && <SystemScreen data={data} onReindex={dashboard.reindex} onBackup={dashboard.backup} />}
          {screen === "detail" && detail && <MemoryDetail memory={detail} onBack={() => setScreen("search")} onArchive={dashboard.archive} onOpenObsidian={dashboard.openObsidian} onOpenFile={dashboard.openFile} onUpdate={dashboard.update} />}
        </main>
      </div>
      <Toaster richColors theme="dark" position="bottom-center" />
    </TooltipProvider>
  )
}

function showError(error: unknown) {
  toast.error(error instanceof Error ? error.message : "The action failed.")
}

function LoadingState() {
  return <div className="grid h-dvh place-items-center bg-background"><div className="text-center"><Database className="mx-auto mb-3 animate-pulse text-foreground" size={28} /><div className="text-sm font-medium">Loading local memory</div><div className="mt-1 text-xs text-muted-foreground">Connecting to the private daemon…</div></div></div>
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return <div className="grid h-dvh place-items-center bg-background"><div className="max-w-md rounded-lg border border-border bg-card p-6 text-center"><WarningCircle className="mx-auto mb-3 text-destructive" size={28} /><h1 className="font-medium">Dashboard session unavailable</h1><p className="mt-2 text-sm leading-relaxed text-muted-foreground">{message}</p><p className="mt-3 rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">Run global-memory dashboard to open a secure session.</p><Button variant="secondary" className="mt-4" onClick={onRetry}><ArrowClockwise />Retry</Button></div></div>
}
