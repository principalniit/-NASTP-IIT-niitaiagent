"use client";

import Link from "next/link";
import { useState } from "react";

import { PageHeader } from "@/components/app/page-header";
import { ErrorState, LoadingState } from "@/components/app/states";
import { AnalysisGate, type AnalysedContext } from "@/components/seo/analysis-gate";
import { IssueTable } from "@/components/seo/issue-table";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useIssues, useLinkRecommendations } from "@/lib/queries";
import { pathOf } from "@/lib/utils";

export function InternalLinkingView() {
  return (
    <AnalysisGate
      header={(picker) => (
        <PageHeader
          title="Internal Linking"
          description="Pages that need more internal links, and contextual links the site's own text already supports."
          actions={picker}
        />
      )}
    >
      {(ctx) => <LinkingBody {...ctx} />}
    </AnalysisGate>
  );
}

function Highlight({ text, phrase }: { text: string; phrase: string }) {
  const index = text.toLowerCase().indexOf(phrase.toLowerCase());
  if (index < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, index)}
      <mark className="rounded bg-primary/15 px-0.5 text-foreground">{text.slice(index, index + phrase.length)}</mark>
      {text.slice(index + phrase.length)}
    </>
  );
}

function LinkingBody({ project, crawl }: AnalysedContext) {
  const [page, setPage] = useState(1);
  const recs = useLinkRecommendations(crawl.id, page);
  const issues = useIssues(project.id, { status: "open", category: "internal_linking", page_size: 50 });
  const totalPages = recs.data ? Math.max(1, Math.ceil(recs.data.total / recs.data.page_size)) : 1;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Suggested contextual links</CardTitle>
          <CardDescription>
            Suggested only where a page already mentions another page&apos;s topic in its own text and does not link to it.
            Nothing is changed on the website; add links you agree with through your content management system.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {recs.isLoading ? (
            <LoadingState />
          ) : recs.error ? (
            <ErrorState error={recs.error} onRetry={() => void recs.refetch()} />
          ) : !recs.data?.items.length ? (
            <p className="text-sm text-muted-foreground">
              No suggestions. Either under-linked pages are not mentioned by name elsewhere, or they are already linked.
            </p>
          ) : (
            <ul className="space-y-4">
              {recs.data.items.map((r) => (
                <li key={r.id} className="rounded-lg border p-4">
                  <p className="text-sm">
                    On{" "}
                    <Link href={`/crawls/${crawl.id}/pages/${r.source_page_id}`} className="font-medium text-primary underline-offset-4 hover:underline">
                      {pathOf(r.source_url)}
                    </Link>
                    , link the words <span className="font-medium">“{r.anchor_text}”</span> to{" "}
                    <Link href={`/crawls/${crawl.id}/pages/${r.target_page_id}`} className="font-medium text-primary underline-offset-4 hover:underline">
                      {pathOf(r.target_url)}
                    </Link>
                    {r.target_title ? <span className="text-muted-foreground"> ({r.target_title})</span> : null}
                  </p>
                  {r.snippet ? (
                    <blockquote className="mt-2 border-l-2 pl-3 text-sm text-muted-foreground">
                      <Highlight text={r.snippet} phrase={r.anchor_text} />
                    </blockquote>
                  ) : null}
                  <p className="mt-2 text-xs text-muted-foreground">{r.reason}</p>
                </li>
              ))}
            </ul>
          )}
          {totalPages > 1 ? (
            <nav aria-label="Suggestions pagination" className="mt-4 flex justify-end gap-2">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((n) => n - 1)}>Previous</Button>
              <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage((n) => n + 1)}>Next</Button>
            </nav>
          ) : null}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Internal linking issues</CardTitle>
          <CardDescription>Orphan pages, under-linked important pages, dead ends and excessive or nofollow links.</CardDescription>
        </CardHeader>
        <CardContent>
          {issues.isLoading ? (
            <LoadingState />
          ) : issues.data?.items.length ? (
            <IssueTable issues={issues.data.items} showCategory={false} />
          ) : (
            <p className="text-sm text-muted-foreground">No open internal linking issues.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
