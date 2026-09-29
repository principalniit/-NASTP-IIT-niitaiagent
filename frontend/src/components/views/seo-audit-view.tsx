"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import Link from "next/link";

import { PageHeader } from "@/components/app/page-header";
import { ErrorState, LoadingState } from "@/components/app/states";
import { AnalysisGate, type AnalysedContext } from "@/components/seo/analysis-gate";
import { IssueTable } from "@/components/seo/issue-table";
import { HeroScore, ScoreMeter } from "@/components/seo/score";
import { SEVERITY_STYLE } from "@/components/seo/severity";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api, ApiError } from "@/lib/api";
import { useCurrentOrg } from "@/lib/current-org";
import { useIssueSummary, useIssues, useScore } from "@/lib/queries";
import { CATEGORY_LABELS, SEVERITIES, type CrawlJob, type IssueCategory } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

const CATEGORIES = Object.keys(CATEGORY_LABELS) as IssueCategory[];

export function SeoAuditView() {
  return (
    <AnalysisGate
      header={(picker) => (
        <PageHeader
          title="SEO Audit"
          description="Health score and priorities from the latest analysed crawl."
          actions={picker}
        />
      )}
    >
      {(ctx) => <AuditBody {...ctx} />}
    </AnalysisGate>
  );
}

function AuditBody({ org, project, crawl }: AnalysedContext) {
  const score = useScore(crawl.id);
  const summary = useIssueSummary(project.id);
  const top = useIssues(project.id, { status: "open", sort: "priority", order: "desc", page_size: 10 });
  const { can } = useCurrentOrg();

  if (score.isLoading) return <LoadingState rows={5} />;
  if (score.error || !score.data) return <ErrorState error={score.error} onRetry={() => void score.refetch()} />;
  const s = score.data;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle>{project.name}</CardTitle>
              <CardDescription>
                Crawl of {formatDateTime(crawl.finished_at ?? crawl.created_at, org.timezone)} · {s.pages_analysed} HTML pages analysed ·{" "}
                <Link href={`/crawls/${crawl.id}`} className="text-primary underline-offset-4 hover:underline">
                  crawl details
                </Link>
              </CardDescription>
            </div>
            {can("crawls:start") ? <ReanalyseButton crawl={crawl} /> : null}
          </div>
        </CardHeader>
        <CardContent className="grid gap-8 md:grid-cols-[minmax(0,14rem)_1fr]">
          <HeroScore value={s.overall} label="Overall SEO health" />
          <div className="space-y-4">
            {CATEGORIES.map((c) => (
              <ScoreMeter key={c} label={CATEGORY_LABELS[c]} value={s[c]} weight={s.breakdown.categories[c]?.weight ?? 0} />
            ))}
          </div>
        </CardContent>
        <CardContent className="border-t pt-4 text-xs text-muted-foreground">
          This score summarises issues this platform found on the crawled pages. It is a site-health indicator for
          prioritising work, not a search engine ranking factor or a prediction of search results.
        </CardContent>
      </Card>

      <section aria-labelledby="open-heading" className="space-y-3">
        <h2 id="open-heading" className="text-lg font-semibold">
          Open issues
        </h2>
        {summary.data ? (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {SEVERITIES.map((sev) => {
              const style = SEVERITY_STYLE[sev];
              const Icon = style.icon;
              return (
                <Link
                  key={sev}
                  href={`/issues?severity=${sev}`}
                  className="rounded-lg border bg-card p-3 transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  aria-label={`${summary.data.open_by_severity[sev]} ${style.label} issues`}
                >
                  <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <Icon className="size-3.5" style={{ color: style.color }} aria-hidden />
                    {style.label}
                  </span>
                  <span className="mt-1 block text-2xl font-semibold tabular-nums">{summary.data.open_by_severity[sev]}</span>
                </Link>
              );
            })}
            <div className="rounded-lg border bg-card p-3">
              <span className="text-xs text-muted-foreground">Resolved in this crawl</span>
              <span className="mt-1 block text-2xl font-semibold tabular-nums">{summary.data.resolved_in_latest}</span>
            </div>
          </div>
        ) : (
          <LoadingState rows={1} />
        )}
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Top priorities</CardTitle>
          <CardDescription>
            Ranked by severity, pages affected, page importance, effort and confidence. Open an issue to see why.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {top.isLoading ? (
            <LoadingState />
          ) : top.data?.items.length ? (
            <>
              <IssueTable issues={top.data.items} />
              <Link href="/issues" className="mt-3 inline-block text-sm font-medium text-primary underline-offset-4 hover:underline">
                View all {top.data.total} open issues
              </Link>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">No open issues were found in the latest analysis.</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>How the score is calculated</CardTitle>
          <CardDescription>
            Each category starts at 100. Every finding subtracts its severity weight multiplied by the share of pages
            it affects. Weights are set in project settings.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6 md:grid-cols-2">
          {CATEGORIES.map((c) => {
            const b = s.breakdown.categories[c];
            if (!b) return null;
            return (
              <div key={c}>
                <h3 className="text-sm font-semibold">
                  {CATEGORY_LABELS[c]} <span className="font-normal text-muted-foreground">· {b.pages_considered} pages considered</span>
                </h3>
                {b.note ? <p className="text-sm text-muted-foreground">{b.note}</p> : null}
                {b.contributions.length === 0 && !b.note ? (
                  <p className="text-sm text-muted-foreground">No deductions.</p>
                ) : (
                  <ul className="mt-1 space-y-0.5 text-sm">
                    {b.contributions.slice(0, 6).map((r) => (
                      <li key={r.rule_id} className="flex justify-between gap-2">
                        <Link href={`/issues?rule_id=${encodeURIComponent(r.rule_id)}`} className="truncate font-mono text-xs text-primary underline-offset-4 hover:underline">
                          {r.rule_id}
                        </Link>
                        <span className="tabular-nums text-muted-foreground">−{(r.penalty * 100).toFixed(1)}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            );
          })}
        </CardContent>
      </Card>
    </div>
  );
}

function ReanalyseButton({ crawl }: { crawl: CrawlJob }) {
  const queryClient = useQueryClient();
  const run = useMutation({
    mutationFn: () => api<CrawlJob>(`/crawls/${crawl.id}/analyse`, { method: "POST" }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["organisations"] }),
  });
  return (
    <div className="space-y-2">
      <Button variant="outline" size="sm" onClick={() => run.mutate()} disabled={run.isPending || run.isSuccess}>
        <RefreshCw aria-hidden /> {run.isSuccess ? "Analysis queued" : "Re-run analysis"}
      </Button>
      {run.error ? (
        <Alert variant="destructive">
          <AlertDescription>{run.error instanceof ApiError ? run.error.message : "Could not queue the analysis."}</AlertDescription>
        </Alert>
      ) : null}
    </div>
  );
}

