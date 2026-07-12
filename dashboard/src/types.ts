export type Screen = "overview" | "review" | "access" | "search" | "projects" | "activity" | "system" | "detail"
export type MemoryVisibility = "standard" | "protected" | "sealed"
export type MemoryPermission = "read" | "edit" | "manage"

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
  visibility: MemoryVisibility
  access_policy: "user_approval" | "per_access"
  allowed_projects: string[]
  max_permission: MemoryPermission
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
  access: AccessState
}

export interface AccessRequestRecord {
  id: string
  agent: string
  project: string | null
  purpose: string
  permission: MemoryPermission
  requested_duration: "once" | "task" | "15m" | "session"
  sealed_match_count: number
  matched_count: number
  matches: AccessMatchRecord[]
  status: "pending" | "approved" | "denied"
  created_at: string
  resolved_at: string | null
  resolution_note: string | null
}

export interface AccessMatchRecord {
  id: string
  title: string
  type: string
  project: string | null
  access_policy: "user_approval" | "per_access"
  max_permission: MemoryPermission
  eligible: boolean
}

export interface AccessGrantRecord {
  id: string
  request_id: string
  agent: string
  project: string | null
  purpose: string
  permission: MemoryPermission
  duration: "once" | "task" | "15m" | "session"
  status: "active" | "revoked" | "expired" | "used"
  created_at: string
  expires_at: string | null
  remaining_uses: number | null
  scope_count: number
}

export interface AccessEventRecord {
  id: number
  request_id: string | null
  grant_id: string | null
  agent: string
  action: string
  purpose: string
  permission: MemoryPermission
  scope: string
  actor: string
  status: string
  created_at: string
}

export interface AccessState {
  requests: AccessRequestRecord[]
  grants: AccessGrantRecord[]
  events: AccessEventRecord[]
}

export interface ClassificationUpdate {
  visibility: MemoryVisibility
  access_policy: "user_approval" | "per_access"
  allowed_projects: string[]
  max_permission: MemoryPermission
}

export interface AccessApproval {
  permission: MemoryPermission
  duration: "once" | "15m" | "task" | "session"
  memory_ids: string[]
}

export interface MemoryUpdate {
  title: string
  body: string
  tags: string[]
  confidence: number
  importance: number
}
