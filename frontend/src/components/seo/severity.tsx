import { AlertCircle, AlertTriangle, Info, OctagonAlert, type LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";
import type { Severity } from "@/lib/types";

// Reserved status colours (dataviz reference palette). Colour is never the only cue:
// every badge pairs an icon with a text label.
export const SEVERITY_STYLE: Record<Severity, { label: string; icon: LucideIcon; color: string }> = {
  critical: { label: "Critical", icon: OctagonAlert, color: "#d03b3b" },
  high: { label: "High", icon: AlertTriangle, color: "#ec835a" },
  medium: { label: "Medium", icon: AlertCircle, color: "#fab219" },
  low: { label: "Low", icon: Info, color: "var(--muted-foreground)" },
  informational: { label: "Info", icon: Info, color: "var(--muted-foreground)" },
};

export function SeverityBadge({ severity, className }: { severity: Severity; className?: string }) {
  const style = SEVERITY_STYLE[severity];
  const Icon = style.icon;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs font-medium text-foreground",
        className,
      )}
    >
      <Icon className="size-3.5" style={{ color: style.color }} aria-hidden />
      {style.label}
    </span>
  );
}
