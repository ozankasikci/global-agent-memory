import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { SearchScreen } from "@/features/search/search-screen"
import type { MemoryRecord } from "@/types"

function memory(overrides: Partial<MemoryRecord> & Pick<MemoryRecord, "id" | "title">): MemoryRecord {
  const { id, title, ...rest } = overrides
  return {
    id,
    title,
    type: "reference",
    scope: "global",
    project: null,
    status: "active",
    visibility: "standard",
    access_policy: "user_approval",
    allowed_projects: [],
    max_permission: "read",
    confidence: 0.8,
    importance: 0.5,
    created_at: "2026-07-12T00:00:00Z",
    updated_at: "2026-07-12T00:00:00Z",
    tags: [],
    links: [],
    source_kind: "manual",
    source_ref: null,
    body: "Memory body",
    summary: "Memory summary",
    evidence: null,
    path: `/tmp/${id}.md`,
    relative_path: `${id}.md`,
    version: "2026-07-12T00:00:00Z",
    possible_duplicates: [],
    conflicts: [],
    ...rest,
  }
}

describe("SearchScreen lifecycle filtering", () => {
  it("shows only active memories and limits agent view to standard visibility", () => {
    render(
      <SearchScreen
        memories={[
          memory({ id: "active-standard", title: "Active standard memory" }),
          memory({ id: "active-protected", title: "Active protected memory", visibility: "protected" }),
          memory({ id: "rejected-standard", title: "Rejected standard memory", status: "rejected" }),
        ]}
        onOpenMemory={vi.fn()}
      />,
    )

    expect(screen.getByText("Active standard memory")).toBeInTheDocument()
    expect(screen.getByText("Active protected memory")).toBeInTheDocument()
    expect(screen.queryByText("Rejected standard memory")).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Agent view" }))
    expect(screen.getByText("Active standard memory")).toBeInTheDocument()
    expect(screen.queryByText("Active protected memory")).not.toBeInTheDocument()
    expect(screen.queryByText("Rejected standard memory")).not.toBeInTheDocument()
  })
})
