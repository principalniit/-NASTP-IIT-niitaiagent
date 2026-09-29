"use client";

import Link from "next/link";

import { NoOrganisation } from "@/components/app/no-organisation";
import { PageHeader } from "@/components/app/page-header";
import { StatTile } from "@/components/app/stat-tile";
import { ErrorState, LoadingState } from "@/components/app/states";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useCurrentOrg } from "@/lib/current-org";
import { useCrawls, useHealth, useIssueSummary, useMembers, useProjects, useScore } from "@/lib/queries";

const NO_CRAWL = "No crawl data yet";
const NOT_SCORED = "Not scored yet";
const SCORE_HINT = "Scores appear after a crawl is analysed.";

function scoreValue(value: number | null | undefined): number | null {
  return value === null || value === undefined ? null : Math.round(value);
}
const STATUS_LABELS: Record<string, string> = {
  queued: "Queued",
  running: "Running",
  cancelling: "Cancelling",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
};

export function OverviewView() {
  const { current, isLoading, error, refetch, can } = useCurrentOrg();
  const canReadProjects = can("projects:read");
  const projects = useProjects(current?.id ?? null, { page: 1 }, canReadProjects);
  const members = useMembers(current?.id ?? null, can("members:read"));
  const health = useHealth();
  const latestCrawl = useCrawls(current?.id ?? null, { page_size: 1 }, canReadProjects);
  const latestAnalysed = useCrawls(
    current?.id ?? null,
    { page_size: 1, analysed: true },
    canReadProjects,
  );
  const analysedCrawl = latestAnalysed.data?.items[0] ?? null;
  const score = useScore(analysedCrawl?.id ?? null);
  const issueSummary = useIssueSummary(analysedCrawl?.project_id ?? null);
  const latestCompleted = useCrawls(
    current?.id ?? null,
    { page_size: 1, status: "completed" },
    canReadProjects,
  );

  if (isLoading) return <LoadingState rows={4} />;
  if (error) return <ErrorState error={error} onRetry={refetch} />;
  if (!current) return <NoOrganisation />;
  const newest = latestCrawl.data?.items[0];
  const completed = latestCompleted.data?.items[0];

  return (
    <>
      <PageHeader title="Overview" description={`${current.name} · SEO health at a glance`} />

      <section aria-labelledby="org-heading" className="mb-8">
        <h2 id="org-heading" className="sr-only">
          Organisation
        </h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatTile
            label="Projects"
            value={canReadProjects ? (projects.data?.total ?? null) : null}
            loading={projects.isLoading}
            emptyText={canReadProjects ? "Unavailable" : "Requires project access"}
          />
          <StatTile
            label="Members"
            value={members.data?.total ?? null}
            loading={members.isLoading}
            emptyText="Unavailable"
          />
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>Database</CardDescription>
              <CardTitle className="text-base">
                {health.data ? (
                  <Badge variant={health.data.database === "ok" ? "success" : "destructive"}>
                    {health.data.database === "ok" ? "Connected" : "Unavailable"}
                  </Badge>
                ) : (
                  <span className="text-sm font-normal text-muted-foreground">Checking…</span>
                )}
              </CardTitle>
            </CardHeader>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardDescription>AI assistant</CardDescription>
              <CardTitle className="text-base">
                {health.data ? (
                  <Badge variant={health.data.ai.status === "available" ? "success" : "secondary"}>
                    {health.data.ai.status === "disabled"
                      ? "Disabled"
                      : health.data.ai.status === "available"
                        ? "Available"
                        : "Unavailable"}
                  </Badge>
                ) : (
                  <span className="text-sm font-normal text-muted-foreground">Checking…</span>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent className="text-xs text-muted-foreground">
              Crawling, analysis and reports work without AI.
            </CardContent>
          </Card>
        </div>
      </section>

      <section aria-labelledby="seo-heading" className="mb-8">
        <h2 id="seo-heading" className="mb-3 text-lg font-semibold">
          SEO health
        </h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatTile
            label="Overall SEO health score"
            value={scoreValue(score.data?.overall)}
            loading={latestAnalysed.isLoading || (!!analysedCrawl && score.isLoading)}
            emptyText={NOT_SCORED}
            hint={analysedCrawl ? `${analysedCrawl.project_name} · site health, not a ranking` : SCORE_HINT}
          />
          <StatTile label="Technical SEO score" value={scoreValue(score.data?.technical)} emptyText={NOT_SCORED} />
          <StatTile label="On-page score" value={scoreValue(score.data?.on_page)} emptyText={NOT_SCORED} />
          <StatTile label="Content score" value={scoreValue(score.data?.content)} emptyText={NOT_SCORED} />
          <StatTile
            label="Critical and high-priority issues"
            value={issueSummary.data && analysedCrawl ? issueSummary.data.open_by_severity.critical + issueSummary.data.open_by_severity.high : null}
            emptyText={NOT_SCORED}
          />
          <StatTile
            label="Pages crawled"
            value={completed ? completed.pages_crawled : null}
            loading={latestCompleted.isLoading}
            emptyText={NO_CRAWL}
            hint={completed ? `Latest completed crawl: ${completed.project_name}` : undefined}
          />
          <StatTile
            label="Crawl status"
            value={newest ? STATUS_LABELS[newest.status] : null}
            loading={latestCrawl.isLoading}
            emptyText="No crawls run"
            hint={newest ? `${newest.project_name}` : undefined}
          />
          <StatTile
            label="Resolved issues"
            value={issueSummary.data && analysedCrawl && issueSummary.data.resolved_total > 0 ? issueSummary.data.resolved_total : null}
            emptyText={analysedCrawl ? "None verified yet" : "Needs two analysed crawls"}
            hint={analysedCrawl ? "Verified by a later crawl" : undefined}
          />
        </div>
      </section>

      <section aria-labelledby="activity-heading" className="grid gap-4 lg:grid-cols-3">
        <h2 id="activity-heading" className="sr-only">
          Activity
        </h2>
        {[
          ["Issue trend", "Plotted once at least two analysed crawls exist (Phase 5)."],
          ["Recent recommendations", "AI-assisted recommendations and drafts arrive in Phase 4. Rule-based recommendations are on each issue."],
          ["Latest reports", "Management reports become available in Phase 5."],
        ].map(([title, text]) => (
          <Card key={title}>
            <CardHeader>
              <CardTitle>{title}</CardTitle>
              <CardDescription>{text}</CardDescription>
            </CardHeader>
          </Card>
        ))}
      </section>

      {canReadProjects && projects.data?.total === 0 ? (
        <p className="mt-8 text-sm text-muted-foreground">
          Start by{" "}
          <Link className="font-medium text-primary underline-offset-4 hover:underline" href="/projects">
            adding a project
          </Link>{" "}
          for the website you want to analyse.
        </p>
      ) : null}
    </>
  );
}
