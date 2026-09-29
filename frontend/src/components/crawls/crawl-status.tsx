import { Badge } from "@/components/ui/badge";
import type { CrawlJob, CrawlStatus } from "@/lib/types";

const LABELS: Record<CrawlStatus, string> = {
  queued: "Queued",
  running: "Running",
  cancelling: "Cancelling",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
};

const VARIANTS: Record<CrawlStatus, "secondary" | "success" | "destructive" | "warning" | "outline"> = {
  queued: "secondary",
  running: "warning",
  cancelling: "warning",
  completed: "success",
  failed: "destructive",
  cancelled: "outline",
};

export function CrawlStatusBadge({ status }: { status: CrawlStatus }) {
  return <Badge variant={VARIANTS[status]}>{LABELS[status]}</Badge>;
}

export function HttpStatus({ code }: { code: number | null }) {
  if (code === null) return <span className="text-muted-foreground">—</span>;
  const variant = code >= 500 || code >= 400 ? "destructive" : code >= 300 ? "warning" : "success";
  return <Badge variant={variant}>{code}</Badge>;
}

/** Progress against the page budget. Discovery can stop early, so this is an upper bound. */
export function CrawlProgress({ job }: { job: CrawlJob }) {
  const max = Math.max(1, job.config.max_pages);
  const done = job.pages_crawled + job.pages_failed + job.pages_blocked;
  const percent = Math.min(100, Math.round((done / max) * 100));
  return (
    <div className="space-y-1.5">
      <div
        role="progressbar"
        aria-label="Crawl progress"
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={done}
        aria-valuetext={`${done} of at most ${max} pages processed`}
        className="h-2 w-full overflow-hidden rounded-full bg-muted"
      >
        <div className="h-full bg-primary transition-all" style={{ width: `${percent}%` }} />
      </div>
      <p className="text-xs text-muted-foreground" aria-live="polite">
        {job.status === "queued"
          ? "Waiting for a worker to start this crawl."
          : `${done} of at most ${max} pages processed · ${job.pages_discovered} discovered`}
      </p>
    </div>
  );
}
