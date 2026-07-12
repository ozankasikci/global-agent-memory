import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"

import { dashboardApi } from "@/lib/api"
import { fixtureDashboard } from "@/lib/fixtures"
import type { AccessApproval, ClassificationUpdate, DashboardData, MemoryRecord, MemoryUpdate } from "@/types"

export function useDashboard() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [project, setProject] = useState<string | undefined>()

  const load = useCallback(async (nextProject?: string) => {
    setLoading(true)
    setError(null)
    try {
      const result = await dashboardApi.bootstrap(nextProject)
      setData(result)
      setProject(result.selected_project ?? undefined)
    } catch (caught) {
      if (import.meta.env.DEV) {
        setData(fixtureDashboard)
        setProject(fixtureDashboard.selected_project ?? undefined)
      } else {
        setError(caught instanceof Error ? caught.message : "The dashboard could not load.")
      }
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const replaceMemory = useCallback((updated: MemoryRecord) => {
    setData((current) => current ? {
      ...current,
      memories: current.memories.map((item) => item.id === updated.id ? updated : item),
      candidates: updated.status === "candidate"
        ? current.candidates.map((item) => item.id === updated.id ? updated : item)
        : current.candidates.filter((item) => item.id !== updated.id),
    } : current)
  }, [])

  const mutate = useCallback(async (operation: () => Promise<MemoryRecord>, success: string) => {
    const updated = await operation()
    replaceMemory(updated)
    toast.success(success)
    return updated
  }, [replaceMemory])

  return {
    data,
    loading,
    error,
    project,
    selectProject(nextProject: string) {
      setProject(nextProject)
      void load(nextProject)
    },
    reload: () => load(project),
    approve: (memory: MemoryRecord, classification: ClassificationUpdate) => mutate(
      () => dashboardApi.approve(memory, classification),
      `Approved “${memory.title}” as ${classification.visibility}`,
    ),
    reject: (memory: MemoryRecord, reason: string) => mutate(() => dashboardApi.reject(memory, reason), `Rejected “${memory.title}”`),
    update: (memory: MemoryRecord, patch: MemoryUpdate) => mutate(() => dashboardApi.update(memory, patch), `Updated “${memory.title}”`),
    archive: (memory: MemoryRecord, reason: string) => mutate(() => dashboardApi.archive(memory, reason), `Archived “${memory.title}”`),
    reindex: async () => {
      const result = await dashboardApi.reindex()
      toast.success(`Reindex complete · ${result.indexed} memories indexed`)
      await load(project)
    },
    backup: async () => {
      const result = await dashboardApi.backup()
      toast.success(`Backup created · ${result.path}`)
    },
    openObsidian: async (memory: MemoryRecord) => {
      await dashboardApi.openObsidian(memory)
      toast.success("Opening memory in Obsidian")
    },
    openFile: async (memory: MemoryRecord) => {
      await dashboardApi.openFile(memory)
      toast.success("Opening Markdown file")
    },
    classify: (memory: MemoryRecord, classification: ClassificationUpdate) => mutate(
      () => dashboardApi.classify(memory, classification),
      `Visibility changed to ${classification.visibility}`,
    ),
    unlock: (memory: MemoryRecord, purpose: string) => dashboardApi.unlock(memory, purpose),
    approveAccess: async (requestId: string, approval: AccessApproval) => {
      const result = await dashboardApi.accessAction(requestId, "approve", approval)
      setData((current) => current ? { ...current, access: result.access } : current)
      toast.success("Temporary access granted")
    },
    denyAccess: async (requestId: string, reason: string) => {
      const result = await dashboardApi.accessAction(requestId, "deny", { reason })
      setData((current) => current ? { ...current, access: result.access } : current)
      toast.success("Access request denied")
    },
    revokeAccess: async (grantId: string) => {
      const result = await dashboardApi.accessAction(grantId, "revoke")
      setData((current) => current ? { ...current, access: result.access } : current)
      toast.success("Access grant revoked")
    },
  }
}
