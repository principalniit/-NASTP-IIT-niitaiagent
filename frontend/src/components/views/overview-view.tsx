"use client";

import Link from "next/link";

import { NoOrganisation } from "@/components/app/no-organisation";
import { PageHeader } from "@/components/app/page-header";
import { StatTile } from "@/components/app/stat-tile";
import { ErrorState, LoadingState } from "@/components/app/states";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useCurrentOrg } from "@/lib/current-org";
import { useHealth, useMembers, useProjects } from "@/lib/queries";

const NO_CRAWL = "No crawl data yet";
const CRAWL_HINT = "Appears after the first crawl (Phase 2) and analysis (Phase 3).";

export function OverviewView() {
  const { current, isLoading, error, refetch, can } = useCurrentOrg();
  const canReadProjects = can("projects:read");
  const projects = useProjects(current?.id ?? null, { page: 1 }, canReadProjects);
  const members = useMembers(current?.id ?? null, can("members:read"));
  const health = useHealth();

  if (isLoading) return <LoadingState rows={4} />;
  if (error) return <ErrorState error={error} onRetry={refetch} />;
  if (!current) return <NoOrganisation />;

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
          <StatTile label="Overall SEO health score" value={null} emptyText={NO_CRAWL} hint={CRAWL_HINT} />
          <StatTile label="Technical SEO score" value={null} emptyText={NO_CRAWL} />
          <StatTile label="On-page score" value={null} emptyText={NO_CRAWL} />
          <StatTile label="Content score" value={null} emptyText={NO_CRAWL} />
          <StatTile label="Critical and high-priority issues" value={null} emptyText={NO_CRAWL} />
          <StatTile label="Pages crawled" value={null} emptyText={NO_CRAWL} />
          <StatTile label="Crawl status" value={null} emptyText="No crawls run" />
          <StatTile label="Resolved issues" value={null} emptyText="Needs two crawls" />
        </div>
      </section>

      <section aria-labelledby="activity-heading" className="grid gap-4 lg:grid-cols-3">
        <h2 id="activity-heading" className="sr-only">
          Activity
        </h2>
        {[
          ["Issue trend", "Plotted once at least two analysed crawls exist (Phase 5)."],
          ["Recent recommendations", "Recommendations are generated from crawl evidence (Phase 4)."],
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
