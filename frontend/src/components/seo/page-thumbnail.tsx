import type { CrawlPageRow } from "@/lib/types";
import { cn } from "@/lib/utils";

type ThumbnailPage = Pick<
  CrawlPageRow,
  | "url"
  | "status_code"
  | "fetch_status"
  | "title"
  | "word_count"
  | "h1_count"
  | "images_missing_alt"
  | "internal_links_count"
  | "is_noindex"
  | "is_orphan"
>;

/** A stable number from the URL, so a page always draws the same way. */
function seed(text: string): number {
  let hash = 2166136261;
  for (let i = 0; i < text.length; i++) hash = Math.imul(hash ^ text.charCodeAt(i), 16777619);
  return hash >>> 0;
}

function tone(page: ThumbnailPage): { bar: string; label: string } {
  if (page.fetch_status !== "fetched" && page.fetch_status !== "not_modified") {
    return { bar: "fill-muted-foreground/40", label: "not fetched" };
  }
  const code = page.status_code ?? 0;
  if (code >= 500) return { bar: "fill-destructive", label: `${code}` };
  if (code >= 400) return { bar: "fill-destructive/80", label: `${code}` };
  if (code >= 300) return { bar: "fill-warning", label: `${code}` };
  return { bar: "fill-primary", label: `${code}` };
}

/**
 * A wireframe of a crawled page, drawn from its own crawl facts: the status sets the
 * bar colour, the title and H1 blocks show whether they exist (dashed when missing),
 * the text lines grow with the word count, dots stand for internal links, and flags mark
 * noindex, orphan pages and images without alt text. It is a picture of the data, not a
 * screenshot: pages are never rendered in a browser.
 */
export function PageThumbnail({ page, className }: { page: ThumbnailPage; className?: string }) {
  const rng = seed(page.url);
  const { bar, label } = tone(page);
  const fetched = page.fetch_status === "fetched" || page.fetch_status === "not_modified";
  const ok = fetched && (page.status_code ?? 0) < 300;
  const titleWidth = page.title ? 30 + Math.min(page.title.length, 70) * 1.3 : 90;
  const words = page.word_count ?? 0;
  const lines = ok ? Math.min(7, Math.round(Math.log2(words + 1) / 1.4)) : 0;
  const links = Math.min(page.internal_links_count, 14);
  const lineWidth = (i: number) => 70 + ((rng >> (i * 3)) % 60);

  return (
    <svg viewBox="0 0 160 120" className={cn("block h-auto w-full", className)} aria-hidden focusable="false">
      <rect x="0.5" y="0.5" width="159" height="119" rx="8" className="fill-card stroke-border" />
      <rect x="0.5" y="0.5" width="159" height="14" rx="8" className={bar} />
      <rect x="0.5" y="8" width="159" height="7" className={bar} />
      <circle cx="8" cy="7.5" r="2" className="fill-white/80" />
      <circle cx="14" cy="7.5" r="2" className="fill-white/60" />
      <circle cx="20" cy="7.5" r="2" className="fill-white/40" />
      <rect x="28" y="4" width="92" height="7" rx="3.5" className="fill-white/25" />
      <text x="152" y="10.5" textAnchor="end" fontSize="7" fontWeight="700" className="fill-white">
        {label}
      </text>

      {fetched ? (
        <>
          {page.title ? (
            <rect x="10" y="22" width={titleWidth} height="7" rx="3" className="fill-foreground/70" />
          ) : (
            <rect x="10" y="22" width={titleWidth} height="7" rx="3" className="fill-none stroke-warning" strokeDasharray="3 2" />
          )}
          {page.h1_count === 0 ? (
            <rect x="10" y="35" width="140" height="22" rx="4" className="fill-none stroke-warning" strokeDasharray="4 3" />
          ) : (
            <>
              <rect x="10" y="35" width="140" height="22" rx="4" className="fill-primary/15" />
              <rect x="16" y="42" width={60 + (rng % 50)} height="8" rx="3" className="fill-primary/70" />
              {page.h1_count > 1 ? <rect x="10" y="35" width="140" height="22" rx="4" className="fill-none stroke-warning" /> : null}
            </>
          )}
          {Array.from({ length: lines }, (_, i) => (
            <rect key={i} x="10" y={63 + i * 6} width={lineWidth(i)} height="3" rx="1.5" className="fill-muted-foreground/35" />
          ))}
          {ok && words === 0 ? (
            <text x="80" y="80" textAnchor="middle" fontSize="7" className="fill-muted-foreground">
              no text
            </text>
          ) : null}
          {Array.from({ length: links }, (_, i) => (
            <circle key={i} cx={12 + i * 10} cy="112" r="2.2" className="fill-primary/60" />
          ))}
        </>
      ) : (
        <g className="stroke-muted-foreground/40">
          <line x1="20" y1="30" x2="140" y2="105" strokeWidth="1.5" />
          <line x1="140" y1="30" x2="20" y2="105" strokeWidth="1.5" />
        </g>
      )}

      <g>
        {page.is_noindex ? <Flag x={116} y={20} text="noindex" /> : null}
        {page.is_orphan ? <Flag x={116} y={page.is_noindex ? 31 : 20} text="orphan" /> : null}
        {page.images_missing_alt > 0 ? (
          <g>
            <rect x="130" y="96" width="22" height="16" rx="3" className="fill-warning/25 stroke-warning" />
            <path d="M133 109l5-5 4 3 3-2 4 4" className="fill-none stroke-warning" strokeWidth="1.2" />
          </g>
        ) : null}
      </g>
    </svg>
  );
}

function Flag({ x, y, text }: { x: number; y: number; text: string }) {
  return (
    <g transform={`translate(${x} ${y})`}>
      <rect width="36" height="9" rx="4.5" className="fill-warning/90" />
      <text x="18" y="6.6" textAnchor="middle" fontSize="6" fontWeight="700" className="fill-black/80">
        {text}
      </text>
    </g>
  );
}

/** The legend for page thumbnails, so colour and shape are never the only explanation. */
export const THUMBNAIL_LEGEND =
  "Thumbnails are drawn from crawl data, not screenshots: bar colour shows the HTTP status, dashed outlines mark a missing title or H1, lines grow with the word count, dots are internal links, and flags mark noindex, orphan pages and images without alt text.";
