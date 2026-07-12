import type { MemoryRecord, ServiceState } from "@/types"

export function formatRelative(value: string): string {
  const timestamp = new Date(value).getTime()
  const seconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000))
  if (seconds < 60) return "just now"
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}d ago`
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric", year: "numeric" }).format(new Date(value))
}

export function confidenceLabel(value: number): string {
  return value.toFixed(2)
}

export function confidenceClass(value: number): string {
  if (value >= 0.8) return "text-success"
  if (value >= 0.65) return "text-warning"
  return "text-destructive"
}

export function confidenceBarClass(value: number): string {
  if (value >= 0.8) return "[&>div]:bg-success"
  if (value >= 0.65) return "[&>div]:bg-warning"
  return "[&>div]:bg-destructive"
}

export function statusDotClass(state: ServiceState | string): string {
  if (state === "operational" || state === "active") return "bg-success"
  if (state === "degraded" || state === "candidate") return "bg-warning"
  return "bg-destructive"
}

export function memoryExcerpt(memory: MemoryRecord): string {
  return memory.summary || memory.body.replace(/^#+\s+.*$/gm, "").replace(/\s+/g, " ").trim().slice(0, 220)
}

export function typeLabel(value: string): string {
  return value.replaceAll("_", " ")
}
