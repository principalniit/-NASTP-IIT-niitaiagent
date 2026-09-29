import { cn } from "@/lib/utils";

/** The headline score: a large figure, never a one-bar chart. */
export function HeroScore({ value, label }: { value: number | null; label: string }) {
  return (
    <div>
      <p className="text-sm text-muted-foreground">{label}</p>
      {value === null ? (
        <p className="mt-1 text-lg text-muted-foreground">Not enough data to score</p>
      ) : (
        <p className="mt-1 flex items-baseline gap-1">
          <span className="text-5xl font-semibold tabular-nums tracking-tight">{Math.round(value)}</span>
          <span className="text-sm text-muted-foreground">/ 100</span>
        </p>
      )}
    </div>
  );
}

/** One category score against a 0 to 100 track, in a single hue. The number is printed. */
export function ScoreMeter({
  label,
  value,
  weight,
  className,
}: {
  label: string;
  value: number | null;
  weight: number;
  className?: string;
}) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <div className="flex items-baseline justify-between gap-2 text-sm">
        <span className="font-medium">{label}</span>
        <span className="tabular-nums text-muted-foreground">
          {value === null ? "not scored" : Math.round(value)}
          <span className="ml-2 text-xs">weight {weight}%</span>
        </span>
      </div>
      <div
        role="meter"
        aria-label={`${label} score`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={value ?? undefined}
        aria-valuetext={value === null ? "not scored" : `${Math.round(value)} out of 100`}
        className="h-2 w-full overflow-hidden rounded-full bg-primary/15"
      >
        {value !== null ? (
          <div className="h-full rounded-full bg-primary" style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
        ) : null}
      </div>
    </div>
  );
}
