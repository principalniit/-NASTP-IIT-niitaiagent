import { useId, type CSSProperties } from "react";

import { cn } from "@/lib/utils";

/**
 * The sign-in illustration: a crawler scanning pages, a rules engine checking them, and a
 * local AI core drafting improvements that a person approves. Pure vector, so it is sharp
 * at any size and needs no remote image. Decorative: it carries no data and no figures,
 * and all motion stops when the visitor prefers reduced motion.
 */
export function SeoHeroScene({ className }: { className?: string }) {
  const id = useId();
  const ref = (name: string) => `url(#${id}-${name})`;
  const delay = (seconds: number): CSSProperties => ({ animationDelay: `${seconds}s` });

  // Network nodes around the AI core, with the delay of each node's pulse.
  const nodes: [number, number, number][] = [
    [210, 190, 0],
    [430, 175, 0.6],
    [470, 330, 1.2],
    [420, 430, 1.8],
    [220, 420, 0.9],
    [170, 310, 1.5],
    [320, 140, 2.1],
    [330, 470, 0.3],
  ];

  return (
    <svg
      viewBox="0 0 640 640"
      className={cn("h-full w-full", className)}
      aria-hidden
      focusable="false"
      preserveAspectRatio="xMidYMid meet"
    >
      <defs>
        <pattern id={`${id}-dots`} width="24" height="24" patternUnits="userSpaceOnUse">
          <circle cx="2" cy="2" r="1.1" fill="white" opacity="0.13" />
        </pattern>
        <radialGradient id={`${id}-core`}>
          <stop offset="0" stopColor="white" />
          <stop offset="0.35" stopColor="oklch(0.85 0.12 210)" />
          <stop offset="1" stopColor="oklch(0.62 0.2 290)" stopOpacity="0" />
        </radialGradient>
        <radialGradient id={`${id}-halo`}>
          <stop offset="0" stopColor="oklch(0.72 0.16 230)" stopOpacity="0.55" />
          <stop offset="1" stopColor="oklch(0.72 0.16 230)" stopOpacity="0" />
        </radialGradient>
        <linearGradient id={`${id}-card`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="white" stopOpacity="0.2" />
          <stop offset="1" stopColor="white" stopOpacity="0.06" />
        </linearGradient>
        <linearGradient id={`${id}-beam`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="oklch(0.78 0.13 190)" stopOpacity="0" />
          <stop offset="0.5" stopColor="oklch(0.78 0.13 190)" stopOpacity="0.75" />
          <stop offset="1" stopColor="oklch(0.78 0.13 190)" stopOpacity="0" />
        </linearGradient>
        <linearGradient id={`${id}-link`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="oklch(0.78 0.13 190)" />
          <stop offset="1" stopColor="oklch(0.62 0.2 290)" />
        </linearGradient>
        <filter id={`${id}-glow`} x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="6" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <clipPath id={`${id}-page`}>
          <rect x="0" y="0" width="176" height="212" rx="14" />
        </clipPath>
      </defs>

      <rect width="640" height="640" fill={ref("dots")} />

      {/* Links between the pages, the rules and the AI core: data flowing inwards. */}
      <g fill="none" stroke={ref("link")} strokeWidth="2" strokeLinecap="round" opacity="0.7">
        <path d="M190 210 C 250 250, 270 270, 300 290" strokeDasharray="4 8" className="animate-flow" />
        <path d="M470 250 C 420 270, 380 285, 345 295" strokeDasharray="4 8" className="animate-flow" style={delay(0.4)} />
        <path d="M320 470 C 320 420, 322 380, 322 345" strokeDasharray="4 8" className="animate-flow" style={delay(0.8)} />
      </g>

      {/* Neural network around the core. */}
      <g stroke="white" strokeOpacity="0.16" strokeWidth="1">
        {nodes.map(([x, y], i) => (
          <line key={`l${i}`} x1={x} y1={y} x2="320" y2="300" />
        ))}
        {nodes.map(([x, y], i) => {
          const [nx, ny] = nodes[(i + 1) % nodes.length];
          return <line key={`m${i}`} x1={x} y1={y} x2={nx} y2={ny} strokeOpacity="0.09" />;
        })}
      </g>
      {nodes.map(([x, y, d], i) => (
        <g key={`n${i}`}>
          <circle cx={x} cy={y} r="10" fill={ref("halo")} className="origin-self animate-pulse-glow" style={delay(d)} />
          <circle cx={x} cy={y} r="3.2" fill="white" opacity="0.9" />
        </g>
      ))}

      {/* The AI core. */}
      <g>
        <circle cx="320" cy="300" r="150" fill={ref("halo")} opacity="0.35" />
        <circle
          cx="320"
          cy="300"
          r="150"
          fill="none"
          stroke="white"
          strokeOpacity="0.2"
          strokeDasharray="2 10"
          className="origin-self animate-spin-slow"
        />
        <circle
          cx="320"
          cy="300"
          r="112"
          fill="none"
          stroke="oklch(0.78 0.13 190)"
          strokeOpacity="0.5"
          strokeWidth="1.5"
          strokeDasharray="40 14 6 14"
          className="origin-self animate-spin-reverse"
        />
        <g className="origin-self animate-spin-slow" style={{ animationDuration: "18s" }}>
          <circle cx="320" cy="300" r="76" fill="none" stroke="white" strokeOpacity="0.14" />
          <circle cx="396" cy="300" r="5" fill="oklch(0.78 0.13 190)" filter={ref("glow")} />
          <circle cx="244" cy="300" r="3.5" fill="oklch(0.62 0.2 290)" />
        </g>
        <circle cx="320" cy="300" r="46" fill={ref("core")} className="origin-self animate-pulse-glow" />
        <g filter={ref("glow")}>
          <circle cx="314" cy="294" r="16" fill="none" stroke="white" strokeWidth="4" />
          <path d="M326 306l13 13" stroke="white" strokeWidth="5" strokeLinecap="round" />
          <path d="M314 284.5l2 5.5 5.5 2-5.5 2-2 5.5-2-5.5-5.5-2 5.5-2z" fill="white" />
        </g>
      </g>

      {/* A crawled page, scanned line by line. */}
      <g className="animate-float">
        <g transform="translate(34 72) rotate(-6 88 106)">
          <rect width="176" height="212" rx="14" fill={ref("card")} stroke="white" strokeOpacity="0.25" />
          <g clipPath={ref("page")}>
            <rect width="176" height="26" fill="white" fillOpacity="0.1" />
            <circle cx="14" cy="13" r="3.5" fill="#ff6b6b" opacity="0.8" />
            <circle cx="26" cy="13" r="3.5" fill="#ffd166" opacity="0.8" />
            <circle cx="38" cy="13" r="3.5" fill="#06d6a0" opacity="0.8" />
            <rect x="52" y="8" width="108" height="10" rx="5" fill="white" fillOpacity="0.15" />
            <rect x="16" y="42" width="112" height="12" rx="4" fill="white" fillOpacity="0.75" />
            <rect x="16" y="64" width="144" height="54" rx="8" fill="oklch(0.62 0.2 290)" fillOpacity="0.35" />
            <path d="M28 106l22-22 16 14 14-10 28 18z" fill="white" fillOpacity="0.35" />
            {[130, 144, 158, 172, 186].map((y, i) => (
              <rect key={y} x="16" y={y} width={[144, 126, 138, 98, 120][i]} height="6" rx="3" fill="white" fillOpacity="0.28" />
            ))}
            <rect x="0" y="0" width="176" height="46" fill={ref("beam")} className="animate-scan" />
          </g>
        </g>
        <Chip x={70} y={300} label="Crawl" dot="oklch(0.78 0.13 190)" />
      </g>

      {/* The rules engine: every check produces evidence. */}
      <g className="animate-float-slow" style={delay(1)}>
        <g transform="translate(440 120) rotate(5 82 96)">
          <rect width="164" height="192" rx="14" fill={ref("card")} stroke="white" strokeOpacity="0.25" />
          <rect x="16" y="16" width="80" height="10" rx="5" fill="white" fillOpacity="0.7" />
          {[44, 76, 108, 140].map((y, i) => (
            <g key={y}>
              <circle cx="28" cy={y + 8} r="9" fill={i === 2 ? "#ffd166" : "oklch(0.78 0.13 190)"} fillOpacity="0.9" />
              {i === 2 ? (
                <path d={`M28 ${y + 3}v6m0 3v.5`} stroke="oklch(0.2 0.07 265)" strokeWidth="2.4" strokeLinecap="round" />
              ) : (
                <path d={`M23.5 ${y + 8}l3 3 6-6`} fill="none" stroke="oklch(0.2 0.07 265)" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
              )}
              <rect x="46" y={y + 2} width={[96, 78, 88, 70][i]} height="6" rx="3" fill="white" fillOpacity="0.55" />
              <rect x="46" y={y + 11} width={[64, 90, 52, 80][i]} height="5" rx="2.5" fill="white" fillOpacity="0.22" />
            </g>
          ))}
        </g>
        <Chip x={470} y={330} label="Analyse" dot="#ffd166" />
      </g>

      {/* A search result improved by an AI draft, waiting for a person to approve it. */}
      <g className="animate-float" style={delay(2)}>
        <g transform="translate(150 486)">
          <rect width="340" height="116" rx="16" fill={ref("card")} stroke="white" strokeOpacity="0.25" />
          <circle cx="26" cy="26" r="9" fill="white" fillOpacity="0.25" />
          <rect x="42" y="21" width="110" height="9" rx="4.5" fill="white" fillOpacity="0.35" />
          <rect x="18" y="46" width="236" height="12" rx="5" fill="oklch(0.82 0.1 240)" />
          <rect x="18" y="68" width="300" height="7" rx="3.5" fill="white" fillOpacity="0.4" />
          <rect x="18" y="82" width="250" height="7" rx="3.5" fill="white" fillOpacity="0.4" />
          <g transform="translate(262 14)">
            <rect width="64" height="22" rx="11" fill="oklch(0.62 0.2 290)" />
            <path d="M14 5l1.6 4.4 4.4 1.6-4.4 1.6L14 17l-1.6-4.4L8 11l4.4-1.6z" fill="white" />
            <text x="24" y="15" fontSize="10" fontWeight="600" fill="white">
              AI draft
            </text>
          </g>
          <rect x="270" y="90" width="2" height="12" fill="white" className="animate-blink" />
        </g>
        <Chip x={196} y={612} label="Human approval" dot="#06d6a0" />
      </g>
    </svg>
  );
}

function Chip({ x, y, label, dot }: { x: number; y: number; label: string; dot: string }) {
  const width = 26 + label.length * 7.2;
  return (
    <g transform={`translate(${x} ${y})`}>
      <rect width={width} height="24" rx="12" fill="oklch(0.2 0.07 265)" fillOpacity="0.75" stroke="white" strokeOpacity="0.25" />
      <circle cx="13" cy="12" r="4" fill={dot} />
      <text x="23" y="16.5" fontSize="11.5" fontWeight="600" fill="white" fillOpacity="0.92">
        {label}
      </text>
    </g>
  );
}
