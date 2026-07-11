export type Screen = "overview" | "review" | "search" | "projects" | "activity" | "system" | "detail"

export type ServiceState = "operational" | "degraded" | "down"

export interface ProjectRecord {
  id: string
  name: string
  aliases: string[]
  roots: string[]
  git_remotes: string[]
  organization: string | null
  active: boolean
}

export interface MemoryRecord {
  id: string
  title: string
  type: string
  scope: string
  project: string | null
  status: string
  confidence: number
  importance: number
  created_at: string
  updated_at: string
  tags: string[]
  links: string[]
  source_kind: string
  source_ref: string | null
  body: string
  summary: string
  evidence: string | null
  path: string
  relative_path: string
  version: string
  possible_duplicates: RelatedMemory[]
  conflicts: RelatedMemory[]
}

export interface RelatedMemory {
  id: string
  title: string
  excerpt: string
  similarity?: number
  status: string
}

export interface ServiceRecord {
  name: string
  detail: string
  state: ServiceState
}

export interface ActivityRecord {
  actor: string
  action: string
  target: string
  created_at: string
  kind: string
}

export interface DashboardStatus {
  package_version: string
  daemon_version: string
  vault_path: string
  document_count: number
  chunk_count: number
  pending_index_jobs: number
  pending_embedding_jobs: number
  watcher_state: string
  embedding_state: string
  vector_state: string
  invalid_note_count: number
  keyword_only: boolean
}

export interface DashboardData {
  projects: ProjectRecord[]
  project_stats: Record<string, { memories: number; candidates: number }>
  selected_project: string | null
  memories: MemoryRecord[]
  candidates: MemoryRecord[]
  status: DashboardStatus
  services: ServiceRecord[]
  activity: ActivityRecord[]
}

export interface MemoryUpdate {
  title: string
  body: string
  tags: string[]
  confidence: number
  importance: number
}
