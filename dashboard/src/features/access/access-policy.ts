import type { AccessMatchRecord, MemoryPermission } from "@/types"

export type AccessDuration = "once" | "15m" | "task" | "session"

export const permissions: MemoryPermission[] = ["read", "edit", "manage"]
export const durations: AccessDuration[] = ["once", "15m", "task", "session"]

const permissionLevel: Record<MemoryPermission, number> = { read: 1, edit: 2, manage: 3 }
const durationLevel: Record<AccessDuration, number> = { once: 1, "15m": 2, task: 3, session: 4 }

export function permissionAllowed(
  permission: MemoryPermission,
  requested: MemoryPermission,
  selected: AccessMatchRecord[],
) {
  return permissionLevel[permission] <= permissionLevel[requested]
    && selected.every((match) => permissionLevel[permission] <= permissionLevel[match.max_permission])
}

export function highestAllowedPermission(requested: MemoryPermission, selected: AccessMatchRecord[]) {
  return [...permissions].reverse().find((permission) => permissionAllowed(permission, requested, selected)) ?? "read"
}

export function durationAllowed(
  duration: AccessDuration,
  requested: AccessDuration,
  selected: AccessMatchRecord[],
) {
  if (durationLevel[duration] > durationLevel[requested]) return false
  return duration === "once" || selected.every((match) => match.access_policy !== "per_access")
}

export function durationLabel(duration: AccessDuration) {
  return ({ once: "One retrieval", "15m": "15 minutes", task: "This task", session: "Agent session" } as const)[duration]
}

export function permissionLabel(permission: MemoryPermission) {
  return permission[0].toUpperCase() + permission.slice(1)
}

export function approvalSummary(
  permission: MemoryPermission,
  duration: AccessDuration,
  selectedCount: number,
) {
  const noun = selectedCount === 1 ? "memory" : "memories"
  return `Allow ${permissionLabel(permission)} for ${durationLabel(duration).toLowerCase()} to ${selectedCount} ${noun}`
}
