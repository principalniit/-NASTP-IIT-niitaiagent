"use client";

import { useEffect, useState } from "react";

import { cn } from "@/lib/utils";

/**
 * A score out of 100 as a ring with the number printed in the middle. The ring fills on
 * first render (no motion when reduced motion is requested). Null means not scored, and
 * the ring stays empty with a note instead of a number.
 */
export function ScoreRing({
  value,
  label,
  size = 132,
  className,
  tone = "brand",
  compact = false,
}: {
  value: number | null;
  label: string;
  size?: number;
  className?: string;
  tone?: "brand" | "light";
  /** Small rings print the number only. */
  compact?: boolean;
}) {
  const [shown, setShown] = useState(0);
  useEffect(() => {
    const frame = requestAnimationFrame(() => setShown(value ?? 0));
    return () => cancelAnimationFrame(frame);
  }, [value]);
  const stroke = compact ? 6 : 10;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const rounded = value === null ? null : Math.round(value);
  const light = tone === "light";
  return (
    <div
      role="img"
      aria-label={rounded === null ? `${label}: not scored yet` : `${label}: ${rounded} out of 100`}
      className={cn("relative inline-flex shrink-0 items-center justify-center", className)}
      style={{ width: size, height: size }}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90" aria-hidden>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={stroke}
          className={light ? "stroke-white/20" : "stroke-primary/15"}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - Math.max(0, Math.min(100, shown)) / 100)}
          className={cn("transition-[stroke-dashoffset] duration-1000 ease-out", light ? "stroke-white" : "stroke-primary")}
        />
      </svg>
      <span className="absolute inset-0 flex flex-col items-center justify-center">
        {rounded === null ? (
          <span className={cn("px-4 text-center text-xs", light ? "text-white/80" : "text-muted-foreground")}>
            {compact ? "—" : "Not scored yet"}
          </span>
        ) : (
          <>
            <span className={cn("font-semibold tabular-nums tracking-tight", compact ? "text-base" : "text-4xl")}>{rounded}</span>
            {compact ? null : <span className={cn("text-xs", light ? "text-white/70" : "text-muted-foreground")}>of 100</span>}
          </>
        )}
      </span>
    </div>
  );
}
