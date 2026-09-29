import { ArrowUpRight, type LucideIcon } from "lucide-react";
import Link from "next/link";

import { cn } from "@/lib/utils";

/** A clickable tile that opens a section. `metric` shows live data only when it exists. */
export function LaunchTile({
  href,
  icon: Icon,
  title,
  description,
  metric,
  className,
  style,
}: {
  href: string;
  icon: LucideIcon;
  title: string;
  description: string;
  metric?: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
}) {
  return (
    <Link
      href={href}
      style={style}
      className={cn(
        "group relative flex flex-col gap-3 overflow-hidden rounded-xl border bg-card p-4 shadow-sm transition-all duration-200 animate-fade-up",
        "hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        className,
      )}
    >
      <span
        className="pointer-events-none absolute -right-10 -top-10 size-28 rounded-full bg-brand-glow/10 opacity-0 blur-2xl transition-opacity duration-300 group-hover:opacity-100"
        aria-hidden
      />
      <span className="flex items-start justify-between gap-2">
        <span className="flex size-10 items-center justify-center rounded-lg bg-gradient-to-br from-brand-violet/15 to-brand-glow/20 text-primary transition-transform duration-200 group-hover:scale-110">
          <Icon className="size-5" aria-hidden />
        </span>
        <ArrowUpRight
          className="size-4 text-muted-foreground transition-transform duration-200 group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-primary"
          aria-hidden
        />
      </span>
      <span>
        <span className="block font-medium">{title}</span>
        <span className="mt-0.5 block text-xs text-muted-foreground">{description}</span>
      </span>
      {metric ? <span className="mt-auto text-sm">{metric}</span> : null}
    </Link>
  );
}
