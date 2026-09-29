import { Globe } from "lucide-react";

import { cn } from "@/lib/utils";

// Approximate display limits. Search engines truncate by pixel width and may rewrite
// snippets, so this is a guide, not a promise of what will be shown.
const TITLE_LIMIT = 60;
const DESCRIPTION_LIMIT = 158;

function clip(text: string, limit: number): string {
  return text.length > limit ? `${text.slice(0, limit - 1).trimEnd()}…` : text;
}

function crumbs(url: string): { host: string; path: string } {
  try {
    const parsed = new URL(url);
    const parts = parsed.pathname.split("/").filter(Boolean);
    return { host: parsed.host, path: parts.length ? ` › ${parts.map(decodeURIComponent).join(" › ")}` : "" };
  } catch {
    return { host: url, path: "" };
  }
}

/** How the page's own title and meta description could look as a search result. */
export function SerpPreview({
  url,
  title,
  description,
  className,
}: {
  url: string;
  title: string | null;
  description: string | null;
  className?: string;
}) {
  const { host, path } = crumbs(url);
  return (
    <figure className={cn("rounded-xl border bg-card p-4 shadow-sm", className)}>
      <div className="flex items-center gap-2">
        <span className="flex size-7 items-center justify-center rounded-full bg-muted">
          <Globe className="size-4 text-muted-foreground" aria-hidden />
        </span>
        <p className="min-w-0 truncate text-xs text-muted-foreground">
          <span className="text-foreground">{host}</span>
          {path}
        </p>
      </div>
      <p className={cn("mt-2 text-lg leading-snug", title ? "text-[#1a0dab] dark:text-[#8ab4f8]" : "italic text-muted-foreground")}>
        {title ? clip(title, TITLE_LIMIT) : "No title: search engines will make one up"}
      </p>
      <p className={cn("mt-1 text-sm leading-relaxed", description ? "text-muted-foreground" : "italic text-muted-foreground")}>
        {description ? clip(description, DESCRIPTION_LIMIT) : "No meta description: search engines will pick text from the page."}
      </p>
      <figcaption className="mt-3 flex flex-wrap gap-x-4 gap-y-1 border-t pt-2 text-xs text-muted-foreground">
        <span>
          Title {title ? `${title.length} characters` : "missing"}
          {title && title.length > TITLE_LIMIT ? " · likely truncated" : ""}
        </span>
        <span>
          Description {description ? `${description.length} characters` : "missing"}
          {description && description.length > DESCRIPTION_LIMIT ? " · likely truncated" : ""}
        </span>
        <span>Approximate preview; search engines may show different text.</span>
      </figcaption>
    </figure>
  );
}
