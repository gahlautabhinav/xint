import type { JobStatus } from "@/lib/types";

const STATUS_CLASS: Record<string, string> = {
  RUNNING: "badge--running",
  COMPLETED: "badge--completed",
  FAILED: "badge--failed",
  PENDING: "badge--pending",
  CANCELLED: "badge--cancelled",
};

export function StatusBadge({ status }: { status: JobStatus | string }) {
  const cls = STATUS_CLASS[status] ?? "badge--pending";
  return (
    <span className={`badge ${cls}`}>
      <span className="badge__dot" aria-hidden />
      {status}
    </span>
  );
}
