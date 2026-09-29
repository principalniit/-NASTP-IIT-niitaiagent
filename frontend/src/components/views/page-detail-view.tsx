"use client";

import { ArrowLeft, ExternalLink } from "lucide-react";
import Link from "next/link";

import { PageHeader } from "@/components/app/page-header";
import { EmptyState, ErrorState, LoadingState } from "@/components/app/states";
import { HttpStatus } from "@/components/crawls/crawl-status";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError } from "@/lib/api";
import { useCrawlPage } from "@/lib/queries";
import { FETCH_STATUS_LABELS, type CrawlLinkRef } from "@/lib/types";
import { pathOf } from "@/lib/utils";

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 border-b py-2 last:border-0 sm:grid-cols-3">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="text-sm break-words sm:col-span-2">{children}</dd>
    </div>
  );
}

function Missing({ text = "Not present" }: { text?: string }) {
  return <span className="text-muted-foreground">{text}</span>;
}

export function PageDetailView({ crawlId, pageId }: { crawlId: string; pageId: string }) {
  const query = useCrawlPage(crawlId, pageId);
  if (query.isLoading) return <LoadingState rows={6} />;
  if (query.error) {
    if (query.error instanceof ApiError && query.error.status === 404) {
      return <EmptyState title="Page not found" />;
    }
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  }
  const page = query.data;
  if (!page) return null;
  const jsonLd = page.structured_data.json_ld ?? [];
  const microdata = page.structured_data.microdata;
  const missingAlt = page.images.filter((image) => !image.has_alt);
  const parsed = page.fetch_status === "fetched" || page.fetch_status === "not_modified";

  return (
    <>
      <Button variant="ghost" size="sm" asChild className="mb-2 -ml-2">
        <Link href={`/crawls/${crawlId}`}>
          <ArrowLeft aria-hidden /> Back to crawl
        </Link>
      </Button>
      <PageHeader
        title={pathOf(page.url)}
        description={page.url}
        actions={
          <Button variant="outline" size="sm" asChild>
            <a href={page.url} target="_blank" rel="noopener noreferrer nofollow">
              Open page <ExternalLink aria-hidden />
              <span className="sr-only">(opens in a new tab)</span>
            </a>
          </Button>
        }
      />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Response</CardTitle>
          </CardHeader>
          <CardContent>
            <dl>
              <Fact label="HTTP status"><HttpStatus code={page.status_code} /></Fact>
              <Fact label="Outcome">{FETCH_STATUS_LABELS[page.fetch_status]}{page.error ? ` — ${page.error}` : ""}</Fact>
              <Fact label="Response time">{page.response_time_ms !== null ? `${page.response_time_ms} ms` : <Missing text="Not measured" />}</Fact>
              <Fact label="Content type">{page.content_type ?? <Missing text="Unknown" />}</Fact>
              <Fact label="Size">{page.content_length !== null ? `${page.content_length.toLocaleString()} bytes` : <Missing text="Unknown" />}</Fact>
              <Fact label="Depth">{page.depth ?? <Missing text="Found via sitemap only" />}</Fact>
              <Fact label="Found via">{page.discovered_via}</Fact>
              <Fact label="In sitemap">{page.in_sitemap ? "Yes" : "No"}{page.is_orphan ? " · orphan (no internal links point here)" : ""}</Fact>
              {page.redirect_chain.length ? (
                <Fact label="Redirects">
                  <ol className="list-decimal space-y-1 pl-4">
                    {page.redirect_chain.map((hop) => (
                      <li key={hop.url}>
                        {hop.status_code} {hop.url}
                      </li>
                    ))}
                    <li>{page.final_url}</li>
                  </ol>
                </Fact>
              ) : null}
            </dl>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Metadata</CardTitle>
            <CardDescription>{parsed ? "As served by the website." : "Not available because the page was not fetched as HTML."}</CardDescription>
          </CardHeader>
          {parsed ? (
            <CardContent>
              <dl>
                <Fact label="Title">
                  {page.title ? `${page.title} (${page.title.length} characters)` : <Missing />}
                  {page.title_count > 1 ? <Badge variant="warning" className="ml-2">{page.title_count} title tags</Badge> : null}
                </Fact>
                <Fact label="Meta description">
                  {page.meta_description ? `${page.meta_description} (${page.meta_description.length} characters)` : <Missing />}
                  {page.meta_description_count > 1 ? <Badge variant="warning" className="ml-2">{page.meta_description_count} tags</Badge> : null}
                </Fact>
                <Fact label="Canonical">
                  {page.canonical_url ?? <Missing />}
                  {page.canonical_count > 1 ? <Badge variant="warning" className="ml-2">{page.canonical_count} canonicals</Badge> : null}
                </Fact>
                <Fact label="Robots">
                  {[page.meta_robots && `meta: ${page.meta_robots}`, page.x_robots_tag && `header: ${page.x_robots_tag}`].filter(Boolean).join(" · ") || <Missing text="No directives" />}
                  {page.is_noindex ? <Badge variant="warning" className="ml-2">noindex</Badge> : null}
                </Fact>
                <Fact label="Language">{page.lang ?? <Missing />}</Fact>
                <Fact label="Word count">{page.word_count ?? <Missing />}</Fact>
                <Fact label="hreflang">
                  {page.hreflang.length ? page.hreflang.map((h) => `${h.hreflang}: ${h.href}`).join(", ") : <Missing />}
                </Fact>
              </dl>
            </CardContent>
          ) : null}
        </Card>
        {parsed ? (
          <>
            <Card>
              <CardHeader>
                <CardTitle>Headings</CardTitle>
                <CardDescription>
                  {page.h1_count} H1 · {page.headings.length} heading{page.headings.length === 1 ? "" : "s"} in document order
                </CardDescription>
              </CardHeader>
              <CardContent>
                {page.headings.length === 0 ? (
                  <Missing text="No headings" />
                ) : (
                  <ul className="space-y-1 text-sm">
                    {page.headings.map((h, i) => (
                      <li key={i} style={{ paddingLeft: `${(h.level - 1) * 0.9}rem` }}>
                        <span className="mr-2 font-mono text-xs text-muted-foreground">H{h.level}</span>
                        {h.text || <Missing text="(empty)" />}
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Images</CardTitle>
                <CardDescription>{page.image_count} images · {missingAlt.length} without an alt attribute</CardDescription>
              </CardHeader>
              <CardContent>
                {page.image_count === 0 ? (
                  <p className="text-sm text-muted-foreground">This page has no images.</p>
                ) : missingAlt.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Every image has an alt attribute. Empty alt text marks decorative images.</p>
                ) : (
                  <ul className="list-disc space-y-1 pl-5 text-sm">
                    {missingAlt.map((image, i) => (
                      <li key={`${image.src}-${i}`} className="break-all">{image.src}</li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
            <Card className="lg:col-span-2">
              <CardHeader>
                <CardTitle>Structured data</CardTitle>
                <CardDescription>Detected only. Validation against schema.org recommendations arrives in Phase 3.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                {jsonLd.length === 0 && !microdata?.count ? <Missing text="No JSON-LD or microdata found" /> : null}
                {jsonLd.map((block, i) => (
                  <div key={i} className="flex flex-wrap items-center gap-2">
                    <Badge variant={block.valid ? "success" : "destructive"}>{block.valid ? "Valid JSON" : "Invalid JSON"}</Badge>
                    <span>JSON-LD {block.types.length ? block.types.join(", ") : "(no @type)"}</span>
                    {block.error ? <span className="text-muted-foreground">{block.error}</span> : null}
                  </div>
                ))}
                {microdata?.count ? (
                  <p>
                    Microdata: {microdata.count} item{microdata.count === 1 ? "" : "s"}
                    {microdata.types.length ? ` (${microdata.types.join(", ")})` : ""}
                  </p>
                ) : null}
              </CardContent>
            </Card>
          </>
        ) : null}
        <LinksCard title="Outgoing links" description={`${page.internal_links_count} internal · ${page.external_links_count} external`} links={page.outlinks} crawlId={crawlId} />
        <LinksCard title="Incoming internal links" description={`${page.inlinks_count} crawled pages link here`} links={page.inlinks} crawlId={crawlId} />
      </div>
    </>
  );
}

function LinksCard({ title, description, links, crawlId }: { title: string; description: string; links: CrawlLinkRef[]; crawlId: string }) {
  return (
    <Card className="lg:col-span-2">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        {links.length === 0 ? (
          <Missing text="None" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>URL</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="hidden md:table-cell">Anchor text</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {links.map((link, i) => (
                <TableRow key={`${link.url}-${i}`}>
                  <TableCell className="max-w-80 truncate">
                    {link.page_id ? (
                      <Link href={`/crawls/${crawlId}/pages/${link.page_id}`} className="text-primary underline-offset-4 hover:underline">
                        {link.is_internal ? pathOf(link.url) : link.url}
                      </Link>
                    ) : (
                      <span title={link.url}>{link.url}</span>
                    )}
                    {!link.is_internal ? <Badge variant="outline" className="ml-2">external</Badge> : null}
                    {link.nofollow ? <Badge variant="outline" className="ml-2">nofollow</Badge> : null}
                  </TableCell>
                  <TableCell>{link.is_internal ? <HttpStatus code={link.status_code} /> : <span className="text-xs text-muted-foreground">Not checked</span>}</TableCell>
                  <TableCell className="hidden text-muted-foreground md:table-cell">{link.anchor_text ?? "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
