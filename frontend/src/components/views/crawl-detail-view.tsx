"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ChevronLeft, ChevronRight, Square } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { PageHeader } from "@/components/app/page-header";
import { StatTile } from "@/components/app/stat-tile";
import { EmptyState, ErrorState, LoadingState } from "@/components/app/states";
import { CrawlProgress, CrawlStatusBadge, HttpStatus } from "@/components/crawls/crawl-status";
import { PagesTable } from "@/components/crawls/pages-table";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, ApiError } from "@/lib/api";
import { useCurrentOrg } from "@/lib/current-org";
import { isActiveCrawl, keys, useBrokenLinks, useCrawl, useCrawlSummary } from "@/lib/queries";
import { FETCH_STATUS_LABELS, type CrawlJob } from "@/lib/types";
import { formatDateTime, formatDuration, pathOf } from "@/lib/utils";

const ROBOTS_LABELS: Record<string, string> = {
  found: "Found and applied",
  not_found: "Not found (everything allowed)",
  unreachable: "Unreachable (nothing crawled)",
};

export function CrawlDetailView({ crawlId }: { crawlId: string }) {
  const crawl = useCrawl(crawlId);
  const { current, can } = useCurrentOrg();

  if (crawl.isLoading) return <LoadingState rows={5} />;
  if (crawl.error) {
    if (crawl.error instanceof ApiError && crawl.error.status === 404) {
      return <EmptyState title="Crawl not found" description="It may belong to another organisation or its project was deleted." />;
    }
    return <ErrorState error={crawl.error} onRetry={() => void crawl.refetch()} />;
  }
  const job = crawl.data;
  if (!job) return null;
  const active = isActiveCrawl(job);
  // Results refresh while the crawl runs and settle once it finishes.
  const version = `${job.status}-${job.pages_crawled + job.pages_failed + job.pages_blocked}`;

  return (
    <>
      <PageHeader
        title={`Crawl of ${job.project_name ?? "project"}`}
        description={`${job.config.root_url} · started ${formatDateTime(job.started_at ?? job.created_at, current?.timezone)}`}
        actions={active && can("crawls:start") && job.status !== "cancelling" ? <CancelButton job={job} /> : null}
      />
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <div className="flex flex-wrap items-center gap-2">
              <CardTitle>Status</CardTitle>
              <CrawlStatusBadge status={job.status} />
              {job.incremental ? <Badge variant="outline">Incremental</Badge> : null}
            </div>
            <CardDescription>
              Duration {formatDuration(job.started_at, job.finished_at)} · limits: {job.config.max_pages} pages,
              depth {job.config.max_depth}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {active ? <CrawlProgress job={job} /> : null}
            {job.error_message ? (
              <Alert variant="destructive">
                <AlertTriangle aria-hidden />
                <AlertDescription>{job.error_message}</AlertDescription>
              </Alert>
            ) : null}
            {job.warnings.length ? (
              <Alert>
                <AlertTriangle aria-hidden />
                <AlertTitle>Notes about this crawl</AlertTitle>
                <AlertDescription>
                  <ul className="list-disc space-y-1 pl-4">
                    {job.warnings.map((w) => (
                      <li key={w}>{w}</li>
                    ))}
                  </ul>
                </AlertDescription>
              </Alert>
            ) : null}
            <dl className="grid gap-3 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-muted-foreground">robots.txt</dt>
                <dd>{job.robots_status ? (ROBOTS_LABELS[job.robots_status] ?? job.robots_status) : "Not checked yet"}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Sitemap URLs found</dt>
                <dd>{job.status === "queued" ? "Not checked yet" : job.sitemap_url_count}</dd>
              </div>
            </dl>
            {job.sitemaps.length ? (
              <ul className="space-y-1 text-sm">
                {job.sitemaps.map((s) => (
                  <li key={s.url} className="flex flex-wrap items-center gap-2">
                    <Badge variant={s.status === "ok" ? "success" : "outline"}>{s.status}</Badge>
                    <span className="break-all">{s.url}</span>
                    {s.status === "ok" ? (
                      <span className="text-muted-foreground">
                        {s.kind === "index" ? "sitemap index" : `${s.url_count} URLs`}
                      </span>
                    ) : s.error ? (
                      <span className="text-muted-foreground">{s.error}</span>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : null}
          </CardContent>
        </Card>

        {job.status !== "queued" ? <SummarySection job={job} version={version} /> : null}

        <Card>
          <CardHeader>
            <CardTitle>Pages</CardTitle>
            <CardDescription>Every URL this crawl recorded, including errors and blocked pages.</CardDescription>
          </CardHeader>
          <CardContent>
            <PagesTable crawlId={job.id} version={version} />
          </CardContent>
        </Card>

        {job.status !== "queued" ? <BrokenLinksCard crawlId={job.id} version={version} /> : null}
      </div>
    </>
  );
}

function CancelButton({ job }: { job: CrawlJob }) {
  const queryClient = useQueryClient();
  const cancel = useMutation({
    mutationFn: () => api<CrawlJob>(`/crawls/${job.id}/cancel`, { method: "POST" }),
    onSuccess: (updated) => {
      queryClient.setQueryData(keys.crawl(job.id), updated);
      void queryClient.invalidateQueries({ queryKey: ["organisations"] });
    },
  });
  return (
    <Button
      variant="outline"
      disabled={cancel.isPending}
      onClick={() => {
        if (window.confirm("Stop this crawl? Pages already crawled are kept.")) cancel.mutate();
      }}
    >
      <Square aria-hidden /> Cancel crawl
    </Button>
  );
}

function SummarySection({ job, version }: { job: CrawlJob; version: string }) {
  const summary = useCrawlSummary(job.id, version);
  if (summary.isLoading) return <LoadingState rows={2} />;
  if (summary.error || !summary.data) return <ErrorState error={summary.error} onRetry={() => void summary.refetch()} />;
  const s = summary.data;
  const count = (key: string) => s.status_classes[key] ?? 0;
  return (
    <section aria-labelledby="summary-heading" className="space-y-4">
      <h2 id="summary-heading" className="text-lg font-semibold">
        What this crawl observed
      </h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile label="Pages recorded" value={s.pages_total} />
        <StatTile label="Client errors (4xx)" value={count("4xx")} />
        <StatTile label="Server errors (5xx)" value={count("5xx")} />
        <StatTile label="Redirects" value={s.redirects} />
        <StatTile label="Broken internal links" value={s.broken_internal_links} />
        <StatTile
          label="Orphan pages"
          value={job.status === "completed" && !job.warnings.some((w) => w.includes("page limit")) ? s.orphan_pages : null}
          emptyText="Not determined"
          hint="In the sitemap but not linked from any crawled page."
        />
        <StatTile label="Noindex pages" value={s.noindex_pages} />
        <StatTile
          label="Average response time"
          value={s.average_response_time_ms !== null ? `${s.average_response_time_ms} ms` : null}
          emptyText="No responses"
        />
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Duplicate content</CardTitle>
          <CardDescription>Pages whose visible text is identical after normalising spacing and case.</CardDescription>
        </CardHeader>
        <CardContent>
          {s.duplicate_content_groups.length === 0 ? (
            <p className="text-sm text-muted-foreground">No pages with identical content were found.</p>
          ) : (
            <ul className="space-y-3 text-sm">
              {s.duplicate_content_groups.map((group) => (
                <li key={group.content_hash} className="rounded-md border p-3">
                  <p className="mb-1 font-medium">{group.urls.length} pages share the same content</p>
                  <ul className="list-disc pl-5 text-muted-foreground">
                    {group.urls.map((u) => (
                      <li key={u} className="break-all">
                        {u}
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
      {Object.keys(s.fetch_statuses).length > 1 ? (
        <p className="text-sm text-muted-foreground">
          Fetch outcomes:{" "}
          {Object.entries(s.fetch_statuses)
            .map(([k, v]) => `${FETCH_STATUS_LABELS[k as keyof typeof FETCH_STATUS_LABELS] ?? k} ${v}`)
            .join(" · ")}
        </p>
      ) : null}
    </section>
  );
}

function BrokenLinksCard({ crawlId, version }: { crawlId: string; version: string }) {
  const [page, setPage] = useState(1);
  const broken = useBrokenLinks(crawlId, page, version);
  const data = broken.data;
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Broken internal links</CardTitle>
        <CardDescription>
          Links between crawled pages whose target returned an error. External links are not checked.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {broken.isLoading ? (
          <LoadingState />
        ) : broken.error ? (
          <ErrorState error={broken.error} onRetry={() => void broken.refetch()} />
        ) : !data?.items.length ? (
          <p className="text-sm text-muted-foreground">No broken internal links were found.</p>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>On page</TableHead>
                  <TableHead>Links to</TableHead>
                  <TableHead>Result</TableHead>
                  <TableHead className="hidden md:table-cell">Anchor text</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((link) => (
                  <TableRow key={`${link.source_page_id}-${link.target_page_id}-${link.anchor_text}`}>
                    <TableCell className="max-w-56 truncate">
                      <Link href={`/crawls/${crawlId}/pages/${link.source_page_id}`} className="text-primary underline-offset-4 hover:underline">
                        {pathOf(link.source_url)}
                      </Link>
                    </TableCell>
                    <TableCell className="max-w-56 truncate">
                      <Link href={`/crawls/${crawlId}/pages/${link.target_page_id}`} className="text-primary underline-offset-4 hover:underline">
                        {pathOf(link.target_url)}
                      </Link>
                    </TableCell>
                    <TableCell>
                      {link.status_code ? <HttpStatus code={link.status_code} /> : <Badge variant="destructive">{FETCH_STATUS_LABELS[link.fetch_status]}</Badge>}
                    </TableCell>
                    <TableCell className="hidden text-muted-foreground md:table-cell">{link.anchor_text ?? "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {totalPages > 1 ? (
              <nav aria-label="Broken links pagination" className="mt-4 flex justify-end gap-2">
                <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((n) => n - 1)}>
                  <ChevronLeft aria-hidden /> Previous
                </Button>
                <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage((n) => n + 1)}>
                  Next <ChevronRight aria-hidden />
                </Button>
              </nav>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}
