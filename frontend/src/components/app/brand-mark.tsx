import { useId } from "react";

import { cn } from "@/lib/utils";

/** The product mark: a search lens with an AI spark, drawn as a crisp vector. */
export function BrandMark({ className }: { className?: string }) {
  const id = useId();
  return (
    <svg viewBox="0 0 40 40" className={cn("size-8 shrink-0", className)} aria-hidden focusable="false">
      <defs>
        <linearGradient id={`${id}-bg`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="oklch(0.62 0.2 290)" />
          <stop offset="1" stopColor="oklch(0.72 0.16 230)" />
        </linearGradient>
      </defs>
      <rect width="40" height="40" rx="11" fill={`url(#${id}-bg)`} />
      <circle cx="18" cy="18" r="8" fill="none" stroke="white" strokeWidth="3" />
      <path d="M24 24l7 7" stroke="white" strokeWidth="3.4" strokeLinecap="round" />
      <path d="M18 13.5l1.2 3.3 3.3 1.2-3.3 1.2-1.2 3.3-1.2-3.3-3.3-1.2 3.3-1.2z" fill="white" />
    </svg>
  );
}
