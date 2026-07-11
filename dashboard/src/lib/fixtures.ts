import type { DashboardData, MemoryRecord } from "@/types"

const now = "2026-07-11T14:22:00Z"

function memory(overrides: Partial<MemoryRecord> & Pick<MemoryRecord, "id" | "title" | "type" | "status">): MemoryRecord {
  return {
    scope: "project",
    project: "Naila",
    confidence: 0.82,
    importance: 0.7,
    created_at: now,
    updated_at: now,
    tags: [],
    links: [],
    source_kind: "ai",
    source_ref: "session · dashboard-design",
    body: "",
    summary: "",
    evidence: null,
    path: `/tmp/${overrides.id}.md`,
    relative_path: `20 Projects/Naila/${overrides.id}.md`,
    version: now,
    possible_duplicates: [],
    conflicts: [],
    ...overrides,
  }
}

const candidates = [
  memory({
    id: "mem_demo_arm64",
    title: "Linux ARM64 deployment workflow",
    type: "convention",
    status: "candidate",
    confidence: 0.82,
    importance: 0.9,
    tags: ["deployment", "arm64", "build", "infra"],
    summary: "Build the Linux ARM64 server binary locally and upload it instead of compiling on the resource-constrained server.",
    body: "# Summary\n\nBuild Linux ARM64 releases locally, verify the checksum, upload the binary, and restart the service.\n\n## Workflow\n\nDo not run the compile step on the production server.",
    evidence: "Previous server-side compilation was resource-constrained and repeatedly failed. Local cross-compilation with binary upload is the verified workflow.",
    source_ref: "session · deploy-arm64-fix · 2026-07-11",
    possible_duplicates: [
      { id: "mem_old_arm64", title: "Deploy ARM64 via local cross-compile", excerpt: "Release binaries are built locally and uploaded.", similarity: 0.78, status: "active" },
    ],
    conflicts: [
      { id: "mem_conflict_arm64", title: "Compile release builds on the deploy server", excerpt: "Older workflow contradicts this candidate.", status: "active" },
    ],
  }),
  memory({
    id: "mem_demo_rg",
    title: "Prefer ripgrep over grep for repository searches",
    type: "convention",
    status: "candidate",
    confidence: 0.91,
    tags: ["search", "tooling", "ripgrep"],
    summary: "Use ripgrep for repository-wide searches because it respects .gitignore and avoids generated output.",
    body: "# Summary\n\nUse `rg` for repository-wide searches. Reserve `grep` for piped or single-file input.",
    evidence: "Repeated repository searches were faster and cleaner with ripgrep.",
    source_ref: "session · search-performance",
  }),
  memory({
    id: "mem_demo_auth",
    title: "Authentication is organization-scoped, not per-user",
    type: "decision",
    status: "candidate",
    confidence: 0.74,
    importance: 0.85,
    tags: ["auth", "security", "permissions"],
    summary: "Authorization resolves against the organization and users inherit organization permissions.",
    body: "# Decision\n\nDo not add per-user grants. Extend the organization policy instead.",
    evidence: "The policy module resolves scopes from the organization record.",
    conflicts: [{ id: "mem_auth_old", title: "Authentication is per-user scoped", excerpt: "An older memory that should be superseded.", status: "active" }],
  }),
  memory({
    id: "mem_demo_ts",
    title: "TypeScript strict mode is enabled repo-wide",
    type: "decision",
    status: "candidate",
    confidence: 0.95,
    tags: ["typescript", "quality"],
    summary: "Every package inherits strict mode from the root tsconfig.",
    body: "# Decision\n\nKeep strict mode enabled and fix types rather than weakening compiler settings.",
    evidence: "The root tsconfig sets strict to true and packages do not override it.",
  }),
]

const active = [
  memory({ id: "mem_active_tests", title: "Tests are required for new features and bug fixes", type: "convention", status: "active", confidence: 0.94, summary: "Every behavior change includes focused tests.", body: "# Convention\n\nAdd focused tests for new behavior and regressions.", tags: ["tests", "quality"] }),
  memory({ id: "mem_active_errors", title: "API errors use RFC 7807 problem details", type: "convention", status: "active", confidence: 0.86, summary: "Errors use application/problem+json.", body: "# Convention\n\nReturn RFC 7807 problem details.", tags: ["api", "errors"] }),
  memory({ id: "mem_active_migrations", title: "Database migrations run through the migrate task", type: "solution", status: "active", confidence: 0.89, summary: "Never edit production schema manually.", body: "# Solution\n\nRun the migration task and verify rollback.", tags: ["database", "migrations"] }),
  memory({ id: "mem_active_secrets", title: "Secrets live in 1Password, never in Git", type: "preference", status: "active", confidence: 0.92, summary: "Runtime secrets are loaded from 1Password.", body: "# Preference\n\nNever commit secret-bearing env files.", tags: ["security", "secrets"] }),
]

export const fixtureDashboard: DashboardData = {
  projects: [{ id: "proj_naila", name: "Naila", aliases: [], roots: ["/Users/ozan/Projects/naila"], git_remotes: [], organization: null, active: true }],
  project_stats: { Naila: { memories: active.length, candidates: candidates.length } },
  selected_project: "Naila",
  candidates,
  memories: [...candidates, ...active],
  status: {
    package_version: "0.1.0",
    daemon_version: "0.1.0",
    vault_path: "/Users/ozan/Documents/Global Agent Memory",
    document_count: 8,
    chunk_count: 18,
    pending_index_jobs: 0,
    pending_embedding_jobs: 0,
    watcher_state: "running",
    embedding_state: "configured",
    vector_state: "available",
    invalid_note_count: 0,
    keyword_only: false,
  },
  services: [
    { name: "Local daemon", detail: "localhost:8765 · private", state: "operational" },
    { name: "Claude Code", detail: "MCP connected", state: "operational" },
    { name: "Codex", detail: "MCP connected", state: "operational" },
    { name: "Ollama", detail: "nomic-embed-text · warming", state: "degraded" },
  ],
  activity: [
    { actor: "claude-code", action: "proposed", target: "Linux ARM64 deployment workflow", created_at: now, kind: "candidate_created" },
    { actor: "codex", action: "proposed", target: "TypeScript strict mode is enabled repo-wide", created_at: "2026-07-10T11:00:00Z", kind: "candidate_created" },
  ],
}
