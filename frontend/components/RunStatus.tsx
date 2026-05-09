import { Badge } from "@/components/ui";
import type { RunStatus } from "@/lib/types";

const TONES: Record<RunStatus, "muted" | "blue" | "amber" | "green" | "red" | "gray"> = {
  queued: "muted",
  running: "blue",
  awaiting_approval: "amber",
  succeeded: "green",
  failed: "red",
  cancelled: "gray",
};

export function RunStatusBadge({ status }: { status: RunStatus }) {
  return <Badge tone={TONES[status]}>{status}</Badge>;
}

export function isTerminalStatus(status: RunStatus): boolean {
  return status === "succeeded" || status === "failed" || status === "cancelled";
}
