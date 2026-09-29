import type { LucideIcon } from "lucide-react";
import Link from "next/link";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

/**
 * A metric tile. When `value` is null the tile shows why no number exists instead of a
 * placeholder, so dashboards never display invented figures. With `href`, the tile links
 * to the screen behind the number.
 */
export function StatTile({
  label,
  value,
  emptyText,
  loading,
  hint,
  icon: Icon,
  href,
  className,
}: {
  label: string;
  value: string | number | null;
  emptyText?: string;
  loading?: boolean;
  hint?: string;
  icon?: LucideIcon;
  href?: string;
  className?: string;
}) {
  return (
    <Card
      role="group"
      aria-label={label}
      className={cn(
        "group relative overflow-hidden transition-all duration-200 animate-fade-up hover:-translate-y-0.5 hover:shadow-md",
        href && "hover:border-primary/40",
        className,
      )}
    >
      <span
        className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-gradient-to-r from-brand-teal via-brand-glow to-brand-violet opacity-0 transition-opacity group-hover:opacity-100"
        aria-hidden
      />
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <CardDescription>{label}</CardDescription>
          {Icon ? (
            <span className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary transition-transform group-hover:scale-110">
              <Icon className="size-4" aria-hidden />
            </span>
          ) : null}
        </div>
        {loading ? (
          <Skeleton className="h-8 w-16" />
        ) : value === null ? (
          <CardTitle className="text-sm font-normal text-muted-foreground">{emptyText ?? "No data yet"}</CardTitle>
        ) : (
          <CardTitle className="text-3xl font-semibold tabular-nums">{value}</CardTitle>
        )}
      </CardHeader>
      {hint ? <CardContent className="text-xs text-muted-foreground">{hint}</CardContent> : null}
      {href ? (
        <Link href={href} className="absolute inset-0 rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          <span className="sr-only">Open {label}</span>
        </Link>
      ) : null}
    </Card>
  );
}
