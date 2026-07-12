import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { CandidateDetail } from "@/features/review/candidate-detail"
import { fixtureDashboard } from "@/lib/fixtures"

describe("CandidateDetail", () => {
  it("chooses visibility before approving a candidate", async () => {
    const candidate = fixtureDashboard.candidates[0]
    const onApprove = vi.fn().mockResolvedValue({ ...candidate, status: "active" })

    render(
      <CandidateDetail
        candidate={candidate}
        position="1 of 1"
        onApprove={onApprove}
        onReject={vi.fn()}
        onUpdate={vi.fn()}
        onOpenMemory={() => {}}
        onPrevious={() => {}}
        onNext={() => {}}
      />,
    )

    fireEvent.click(screen.getByRole("button", { name: "Approve" }))
    const dialog = screen.getByRole("dialog")
    fireEvent.click(within(dialog).getByRole("button", { name: /Protected/ }))
    fireEvent.click(within(dialog).getByRole("button", { name: "Approve" }))

    await waitFor(() => expect(onApprove).toHaveBeenCalledWith(candidate, {
      visibility: "protected",
      access_policy: "user_approval",
      allowed_projects: ["Naila"],
      max_permission: "read",
    }))
  })
})
