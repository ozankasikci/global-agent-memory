import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { ClassificationDialog } from "@/features/memory/classification-dialog"
import type { MemoryRecord, ProjectRecord } from "@/types"

const project: ProjectRecord = {
  id: "proj_naila",
  name: "Naila",
  aliases: [],
  roots: [],
  git_remotes: [],
  organization: null,
  active: true,
}

const memory: MemoryRecord = {
  id: "mem_protected",
  title: "Production deployment topology",
  type: "reference",
  scope: "project",
  project: "Naila",
  status: "active",
  visibility: "protected",
  access_policy: "user_approval",
  allowed_projects: ["Naila"],
  max_permission: "read",
  confidence: 0.9,
  importance: 0.8,
  created_at: "2026-07-11T14:22:00Z",
  updated_at: "2026-07-11T14:22:00Z",
  tags: [],
  links: [],
  source_kind: "manual",
  source_ref: null,
  body: "Protected body",
  summary: "Protected summary",
  evidence: null,
  path: "/tmp/memory.md",
  relative_path: "memory.md",
  version: "2026-07-11T14:22:00Z",
  possible_duplicates: [],
  conflicts: [],
}

describe("ClassificationDialog", () => {
  it("saves maximum permission, per-access policy, and locked project scope", async () => {
    const onSave = vi.fn().mockResolvedValue(memory)
    render(<ClassificationDialog memory={memory} projects={[project]} open onOpenChange={() => {}} onSave={onSave} />)

    fireEvent.click(screen.getByRole("button", { name: "Manage" }))
    fireEvent.click(screen.getByRole("button", { name: /Ask every retrieval/ }))
    expect(screen.getByText("Locked to Naila")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Save classification" }))

    await waitFor(() => expect(onSave).toHaveBeenCalledWith({
      visibility: "protected",
      access_policy: "per_access",
      allowed_projects: ["Naila"],
      max_permission: "manage",
    }))
  })
})
