import { Bot, CheckCircle2, CircleDashed, Clock, RotateCcw, Upload, User, XCircle, type LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";
import { DRAFT_STATUS_LABELS, type DraftStatus } from "@/lib/types";

// Status is shown with an icon and a label, never colour alone.
const STYLE: Record<DraftStatus, { icon: LucideIcon; className: string }> = {
  draft: { icon: CircleDashed, className: "text-muted-foreground" },
  pending_review: { icon: Clock, className: "text-foreground" },
  approved: { icon: CheckCircle2, className: "text-success" },
  rejected: { icon: XCircle, className: "text-destructive" },
  published: { icon: Upload, className: "text-success" },
  rolled_back: { icon: RotateCcw, className: "text-muted-foreground" },
};

export function DraftStatusBadge({ status }: { status: DraftStatus }) {
  const { icon: Icon, className } = STYLE[status];
  return (
    <span className="inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs font-medium whitespace-nowrap">
      <Icon className={cn("size-3.5", className)} aria-hidden />
      {DRAFT_STATUS_LABELS[status]}
    </span>
  );
}

export function DraftSourceLabel({ source }: { source: "ai" | "human" }) {
  const Icon = source === "ai" ? Bot : User;
  return (
    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground whitespace-nowrap">
      <Icon className="size-3.5" aria-hidden /> {source === "ai" ? "AI draft" : "Written by a person"}
    </span>
  );
}
