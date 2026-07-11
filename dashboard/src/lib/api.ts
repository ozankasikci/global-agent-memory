import type { DashboardData, MemoryRecord, MemoryUpdate } from "@/types"

interface Envelope<T> {
  ok: boolean
  data?: T
  error?: {
    code: string
    message: string
    remediation?: string
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/ui/api${path}`, {
    credentials: "same-origin",
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-GAM-Action": "dashboard",
      ...init?.headers,
    },
  })
  const envelope = (await response.json()) as Envelope<T>
  if (!response.ok || !envelope.ok || envelope.data === undefined) {
    const error = new Error(envelope.error?.message ?? `Dashboard request failed (${response.status})`)
    error.name = envelope.error?.code ?? "DashboardError"
    throw error
  }
  return envelope.data
}

export const dashboardApi = {
  bootstrap(project?: string) {
    const query = project ? `?project=${encodeURIComponent(project)}` : ""
    return request<DashboardData>(`/bootstrap${query}`)
  },
  approve(memory: MemoryRecord) {
    return request<MemoryRecord>(`/memories/${encodeURIComponent(memory.id)}/approve`, {
      method: "POST",
      body: JSON.stringify({ expected_updated_at: memory.version }),
    })
  },
  reject(memory: MemoryRecord, reason: string) {
    return request<MemoryRecord>(`/memories/${encodeURIComponent(memory.id)}/reject`, {
      method: "POST",
      body: JSON.stringify({ expected_updated_at: memory.version, reason }),
    })
  },
  update(memory: MemoryRecord, patch: MemoryUpdate) {
    return request<MemoryRecord>(`/memories/${encodeURIComponent(memory.id)}`, {
      method: "PATCH",
      body: JSON.stringify({
        expected_updated_at: memory.version,
        metadata_patch: {
          title: patch.title,
          tags: patch.tags,
          confidence: patch.confidence,
          importance: patch.importance,
        },
        body: patch.body,
      }),
    })
  },
  archive(memory: MemoryRecord, reason: string) {
    return request<MemoryRecord>(`/memories/${encodeURIComponent(memory.id)}/archive`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    })
  },
  reindex() {
    return request<{ indexed: number }>("/reindex", { method: "POST", body: "{}" })
  },
  backup() {
    return request<{ path: string }>("/backup", { method: "POST", body: "{}" })
  },
  openObsidian(memory: MemoryRecord) {
    return request<{ obsidian_uri: string }>(`/memories/${encodeURIComponent(memory.id)}/open-obsidian`, {
      method: "POST",
      body: "{}",
    })
  },
  openFile(memory: MemoryRecord) {
    return request<{ file_uri: string }>(`/memories/${encodeURIComponent(memory.id)}/open-file`, {
      method: "POST",
      body: "{}",
    })
  },
}
