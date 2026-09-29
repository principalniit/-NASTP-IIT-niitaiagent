"use client";

import { ChevronLeft, ChevronRight, LayoutGrid, Rows3, Search } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { HttpStatus } from "@/components/crawls/crawl-status";
import { EmptyState, ErrorState, LoadingState } from "@/components/app/states";
import { PageThumbnail, THUMBNAIL_LEGEND } from "@/components/seo/page-thumbnail";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useCrawlPages, type PageFilters } from "@/lib/queries";
import { FETCH_STATUS_LABELS, type CrawlPageRow, type FetchStatus } from "@/lib/types";
import { pathOf } from "@/lib/utils";

const QUICK_FILTERS: Record<string, Pick<PageFilters, "status_class" | "fetch_status" | "orphan" | "noindex" | "in_sitemap">> = {
  all: {},
  "2xx": { status_class: "2xx" },
  "3xx": { status_class: "3xx" },
  "4xx": { status_class: "4xx" },
  "5xx": { status_class: "5xx" },
  failed: { fetch_status: "error" },
  robots: { fetch_status: "blocked_by_robots" },
  noindex: { noindex: "true" },
  orphan: { orphan: "true" },
  sitemap: { in_sitemap: "true" },
};

export function PagesTable({ crawlId, version }: { crawlId: string; version: string }) {
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState("all");
  const [sort, setSort] = useState("url-asc");
  const [page, setPage] = useState(1);
  const [layout, setLayout] = useState("table");

  useEffect(() => {
    const t = setTimeout(() => {
      setQ(search);
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const [sortField, order] = sort.split("-");
  const pages = useCrawlPages(crawlId, { ...QUICK_FILTERS[filter], q, sort: sortField, order, page }, version);
  const data = pages.data;
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 md:flex-row">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-2.5 size-4 text-muted-foreground" aria-hidden />
          <label htmlFor="page-search" className="sr-only">
            Search pages by URL or title
          </label>
          <Input
            id="page-search"
            className="pl-9"
            placeholder="Search URL or title"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <label htmlFor="page-filter" className="sr-only">
          Filter pages
        </label>
        <NativeSelect
          id="page-filter"
          className="md:w-52"
          value={filter}
          onChange={(e) => {
            setFilter(e.target.value);
            setPage(1);
          }}
        >
          <option value="all">All pages</option>
          <option value="2xx">Status 2xx</option>
          <option value="3xx">Redirects (3xx)</option>
          <option value="4xx">Client errors (4xx)</option>
          <option value="5xx">Server errors (5xx)</option>
          <option value="failed">Fetch errors</option>
          <option value="robots">Blocked by robots.txt</option>
          <option value="noindex">Noindex</option>
          <option value="orphan">Orphan pages</option>
          <option value="sitemap">In sitemap</option>
        </NativeSelect>
        <label htmlFor="page-sort" className="sr-only">
          Sort pages
        </label>
        <NativeSelect
          id="page-sort"
          className="md:w-52"
          value={sort}
          onChange={(e) => {
            setSort(e.target.value);
            setPage(1);
          }}
        >
          <option value="url-asc">URL A–Z</option>
          <option value="status_code-desc">Status (highest first)</option>
          <option value="response_time_ms-desc">Slowest first</option>
          <option value="word_count-asc">Fewest words first</option>
          <option value="depth-asc">Shallowest first</option>
          <option value="inlinks_count-asc">Fewest inbound links</option>
        </NativeSelect>
      </div>
      {pages.isLoading ? (
        <LoadingState />
      ) : pages.error ? (
        <ErrorState error={pages.error} onRetry={() => void pages.refetch()} />
      ) : !data || data.items.length === 0 ? (
        <EmptyState title="No pages match" description={q || filter !== "all" ? "Try another filter or search." : "This crawl has not recorded any pages yet."} />
      ) : (
        <Tabs value={layout} onValueChange={setLayout}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <TabsList label="Page layout">
              <TabsTrigger value="table">
                <Rows3 aria-hidden /> Table
              </TabsTrigger>
              <TabsTrigger value="gallery">
                <LayoutGrid aria-hidden /> Gallery
              </TabsTrigger>
            </TabsList>
            <p className="max-w-xl text-xs text-muted-foreground">{THUMBNAIL_LEGEND}</p>
          </div>
          <TabsContent value="table">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="hidden w-20 sm:table-cell">
                    <span className="sr-only">Thumbnail</span>
                  </TableHead>
                  <TableHead>URL</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="hidden lg:table-cell">Title</TableHead>
                  <TableHead className="hidden md:table-cell text-right">Words</TableHead>
                  <TableHead className="hidden md:table-cell text-right">Time (ms)</TableHead>
                  <TableHead className="hidden xl:table-cell text-right">Inbound</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((p) => (
                  <TableRow key={p.id} className="group">
                    <TableCell className="hidden sm:table-cell">
                      <PageThumbnail page={p} className="w-16 transition-transform duration-200 group-hover:scale-110" />
                    </TableCell>
                    <TableCell className="max-w-72">
                      <Link
                        href={`/crawls/${crawlId}/pages/${p.id}`}
                        className="block truncate font-medium text-primary underline-offset-4 hover:underline"
                        title={p.url}
                      >
                        {pathOf(p.url)}
                      </Link>
                      <PageFlags page={p} />
                    </TableCell>
                    <TableCell>
                      <HttpStatus code={p.status_code} />
                    </TableCell>
                    <TableCell className="hidden max-w-64 truncate text-muted-foreground lg:table-cell">
                      {p.title ?? "—"}
                    </TableCell>
                    <TableCell className="hidden text-right tabular-nums md:table-cell">{p.word_count ?? "—"}</TableCell>
                    <TableCell className="hidden text-right tabular-nums md:table-cell">{p.response_time_ms ?? "—"}</TableCell>
                    <TableCell className="hidden text-right tabular-nums xl:table-cell">{p.inlinks_count}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TabsContent>
          <TabsContent value="gallery">
            <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {data.items.map((p, i) => (
                <li key={p.id} className="animate-fade-up" style={{ animationDelay: `${Math.min(i, 12) * 40}ms` }}>
                  <Link
                    href={`/crawls/${crawlId}/pages/${p.id}`}
                    className="group block h-full overflow-hidden rounded-xl border bg-card shadow-sm transition-all hover:-translate-y-1 hover:border-primary/40 hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <span className="block bg-muted/50 p-3">
                      <PageThumbnail page={p} className="transition-transform duration-300 group-hover:scale-[1.03]" />
                    </span>
                    <span className="block space-y-1 p-3">
                      <span className="flex items-center justify-between gap-2">
                        <span className="truncate font-medium text-primary" title={p.url}>
                          {pathOf(p.url)}
                        </span>
                        <HttpStatus code={p.status_code} />
                      </span>
                      <span className="block truncate text-xs text-muted-foreground">{p.title ?? "No title"}</span>
                      <span className="block text-xs text-muted-foreground tabular-nums">
                        {p.word_count ?? 0} words · {p.internal_links_count} internal links · {p.inlinks_count} inbound
                      </span>
                      <PageFlags page={p} />
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </TabsContent>
          <nav aria-label="Pages pagination" className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">
              {data.total} page{data.total === 1 ? "" : "s"} · page {page} of {totalPages}
            </span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((n) => n - 1)}>
                <ChevronLeft aria-hidden /> Previous
              </Button>
              <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage((n) => n + 1)}>
                Next <ChevronRight aria-hidden />
              </Button>
            </div>
          </nav>
        </Tabs>
      )}
    </div>
  );
}

function PageFlags({ page }: { page: CrawlPageRow }) {
  return (
    <span className="mt-1 flex flex-wrap gap-1">
      {page.fetch_status !== "fetched" ? <Badge variant="outline">{FETCH_STATUS_LABELS[page.fetch_status as FetchStatus]}</Badge> : null}
      {page.is_noindex ? <Badge variant="warning">noindex</Badge> : null}
      {page.is_orphan ? <Badge variant="warning">orphan</Badge> : null}
    </span>
  );
}
