import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { RequestDialog } from "@/features/access/access-screen"
import type { AccessRequestRecord } from "@/types"

const baseRequest: AccessRequestRecord = {
  id: "req_test",
  agent: "Claude Code",
  project: "Naila",
  purpose: "Investigate deployment failure",
  permission: "manage",
  requested_duration: "task",
  sealed_match_count: 1,
  matched_count: 1,
  matches: [{
    id: "mem_protected",
    title: "Production deployment topology",
    type: "reference",
    project: "Naila",
    access_policy: "user_approval",
    max_permission: "edit",
    eligible: true,
  }],
  status: "pending",
  created_at: "2026-07-11T14:22:00Z",
  resolved_at: null,
  resolution_note: null,
}

describe("RequestDialog", () => {
  it("requires explicit scope and sends a downgraded least-privilege approval", async () => {
    const onApprove = vi.fn().mockResolvedValue(undefined)
    render(<RequestDialog request={baseRequest} onClose={() => {}} onApprove={onApprove} onDeny={vi.fn()} />)

    const allow = screen.getByRole("button", { name: "Allow" })
    expect(allow).toBeDisabled()

    fireEvent.click(screen.getByRole("checkbox", { name: "Select Production deployment topology" }))
    await waitFor(() => expect(screen.getByRole("button", { name: "Manage" })).toBeDisabled())
    expect(screen.getByText("Allow Edit for this task to 1 memory.")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "15 minutes" }))
    fireEvent.click(allow)
    await waitFor(() => expect(onApprove).toHaveBeenCalledWith("req_test", {
      permission: "edit",
      duration: "15m",
      memory_ids: ["mem_protected"],
    }))
  })

  it("forces one retrieval when any selected memory uses per-access approval", async () => {
    const request: AccessRequestRecord = {
      ...baseRequest,
      matches: [{ ...baseRequest.matches[0], access_policy: "per_access", max_permission: "manage" }],
    }
    render(<RequestDialog request={request} onClose={() => {}} onApprove={vi.fn()} onDeny={vi.fn()} />)

    fireEvent.click(screen.getByRole("checkbox", { name: "Select Production deployment topology" }))
    await waitFor(() => expect(screen.getByRole("button", { name: "15 minutes" })).toBeDisabled())
    expect(screen.getByText("Allow Manage for one retrieval to 1 memory.")).toBeInTheDocument()
  })

  it("disables permissions and durations above the agent request", () => {
    const request: AccessRequestRecord = {
      ...baseRequest,
      permission: "read",
      requested_duration: "15m",
      matches: [{ ...baseRequest.matches[0], max_permission: "manage" }],
    }
    render(<RequestDialog request={request} onClose={() => {}} onApprove={vi.fn()} onDeny={vi.fn()} />)

    expect(screen.getByRole("button", { name: "Edit" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "Manage" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "This task" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "Agent session" })).toBeDisabled()
  })
})
