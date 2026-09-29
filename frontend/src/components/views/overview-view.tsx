"use client";

import {
  Activity,
  BarChart3,
  Bot,
  Database,
  FileText,
  FolderKanban,
  LayoutGrid,
  Network,
  Play,
  TrendingUp,
  Users,
} from "lucide-react";
import Link from "next/link";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { LaunchTile } from "@/components/app/launch-tile";
import { NoOrganisation } from "@/components/app/no-organisation";
import { ScoreRing } from "@/components/app/score-ring";
import { StatTile } from "@/components/app/stat-tile";
import { EmptyState, ErrorState, LoadingState } from "@/components/app/states";
import { SeoHeroScene } from "@/components/login/seo-hero-scene";
import { SEVERITY_STYLE } from "@/components/seo/severity";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useCurrentOrg } from "@/lib/current-org";
import { NAV_GROUPS, NAV_ITEMS } from "@/lib/navigation";
import {
  useAIStatus,
  useCrawls,
  useHealth,
  useIssueSummary,
  useMembers,
  useProjects,
  useReports,
  useScore,
  useScoreHistory,
} from "@/lib/queries";
import { useSession } from "@/lib/session";
import type { CrawlJob, Severity } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

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

function greeting(): string {
  const hour = new Date().getHours();
  return hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
}

export function OverviewView() {
  const { current, isLoading, error, refetch, can } = useCurrentOrg();
  const { me } = useSession();
  const canReadProjects = can("projects:read");
  const projects = useProjects(current?.id ?? null, { page: 1 }, canReadProjects);
  const members = useMembers(current?.id ?? null, can("members:read"));
  const health = useHealth();
  const ai = useAIStatus(current?.id ?? null);
  const latestCrawl = useCrawls(current?.id ?? null, { page_size: 1 }, canReadProjects);
  const latestAnalysed = useCrawls(current?.id ?? null, { page_size: 1, analysed: true }, canReadProjects);
  const analysedCrawl = latestAnalysed.data?.items[0] ?? null;
  const score = useScore(analysedCrawl?.id ?? null);
  const issueSummary = useIssueSummary(analysedCrawl?.project_id ?? null);
  const latestCompleted = useCrawls(current?.id ?? null, { page_size: 1, status: "completed" }, canReadProjects);

  if (isLoading) return <LoadingState rows={4} />;
  if (error) return <ErrorState error={error} onRetry={refetch} />;
  if (!current) return <NoOrganisation />;
  const newest = latestCrawl.data?.items[0];
  const completed = latestCompleted.data?.items[0];
  const firstName = me?.user.full_name.split(/\s+/)[0];

  return (
    <>
      <section
        aria-labelledby="overview-title"
        className="relative isolate mb-8 overflow-hidden rounded-2xl bg-brand-gradient p-6 text-white shadow-lg sm:p-8"
      >
        <div className="pointer-events-none absolute -right-24 -top-16 -z-10 hidden size-[26rem] opacity-30 md:block" aria-hidden>
          <SeoHeroScene />
        </div>
        <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
          <div className="max-w-xl animate-fade-up">
            <p className="text-sm text-white/70">
              {greeting()}
              {firstName ? `, ${firstName}` : ""}
            </p>
            <h1 id="overview-title" className="mt-1 text-3xl font-semibold tracking-tight">
              Overview
            </h1>
            <p className="mt-2 text-sm text-white/80">
              {current.name} · SEO health at a glance.{" "}
              {analysedCrawl
                ? `Latest analysis: ${analysedCrawl.project_name}${analysedCrawl.finished_at ? `, crawled ${formatDateTime(analysedCrawl.finished_at, current.timezone)}` : ""}.`
                : "Run and analyse a crawl to see scores here."}
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              <Button asChild size="sm" className="bg-white text-brand-deep hover:bg-white/90">
                <Link href="/crawls">
                  <Play aria-hidden /> Start a crawl
                </Link>
              </Button>
              <Button asChild size="sm" variant="outline" className="border-white/30 bg-white/10 text-white hover:bg-white/20 hover:text-white">
                <Link href="/issues">Review issues</Link>
              </Button>
              <Button asChild size="sm" variant="outline" className="border-white/30 bg-white/10 text-white hover:bg-white/20 hover:text-white">
                <Link href="/reports">Generate a report</Link>
              </Button>
            </div>
          </div>
          <div className="flex items-center gap-4 self-start rounded-2xl border border-white/15 bg-white/10 p-4 backdrop-blur md:self-auto">
            <ScoreRing value={scoreValue(score.data?.overall)} label="Overall SEO health" tone="light" size={120} />
            <div className="max-w-40 text-sm">
              <p className="font-medium">Overall SEO health</p>
              <p className="mt-1 text-xs text-white/70">Site health for prioritising work, not a search ranking.</p>
            </div>
          </div>
        </div>
      </section>

      <section aria-labelledby="org-heading" className="mb-8">
        <h2 id="org-heading" className="sr-only">
          Organisation
        </h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatTile
            label="Projects"
            icon={FolderKanban}
            href={canReadProjects ? "/projects" : undefined}
            value={canReadProjects ? (projects.data?.total ?? null) : null}
            loading={projects.isLoading}
            emptyText={canReadProjects ? "Unavailable" : "Requires project access"}
          />
          <StatTile
            label="Members"
            icon={Users}
            value={members.data?.total ?? null}
            loading={members.isLoading}
            emptyText="Unavailable"
          />
          <Card className="animate-fade-up transition-all hover:-translate-y-0.5 hover:shadow-md">
            <CardHeader className="pb-2">
              <div className="flex items-start justify-between gap-2">
                <CardDescription>Database</CardDescription>
                <span className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Database className="size-4" aria-hidden />
                </span>
              </div>
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
          <Card className="animate-fade-up transition-all hover:-translate-y-0.5 hover:shadow-md">
            <CardHeader className="pb-2">
              <div className="flex items-start justify-between gap-2">
                <CardDescription>AI assistant</CardDescription>
                <span className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Bot className="size-4" aria-hidden />
                </span>
              </div>
              <CardTitle className="text-base">
                {ai.data ? (
                  <Badge variant={ai.data.status === "available" ? "success" : "secondary"}>
                    {ai.data.status === "disabled" ? "Disabled" : ai.data.status === "available" ? "Available" : "Unavailable"}
                  </Badge>
                ) : (
                  <span className="text-sm font-normal text-muted-foreground">Checking…</span>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent className="text-xs text-muted-foreground">
              {ai.data?.status === "available" ? `Model ${ai.data.model}. ` : ai.data?.detail ? `${ai.data.detail} ` : ""}
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
            icon={Activity}
            href={analysedCrawl ? "/audit" : undefined}
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
            href={analysedCrawl ? `/issues?project=${analysedCrawl.project_id}` : undefined}
            value={
              issueSummary.data && analysedCrawl
                ? issueSummary.data.open_by_severity.critical + issueSummary.data.open_by_severity.high
                : null
            }
            emptyText={NOT_SCORED}
          />
          <StatTile
            label="Pages crawled"
            icon={FileText}
            href={completed ? "/pages" : undefined}
            value={completed ? completed.pages_crawled : null}
            loading={latestCompleted.isLoading}
            emptyText={NO_CRAWL}
            hint={completed ? `Latest completed crawl: ${completed.project_name}` : undefined}
          />
          <StatTile
            label="Crawl status"
            icon={Network}
            href={newest ? `/crawls/${newest.id}` : undefined}
            value={newest ? STATUS_LABELS[newest.status] : null}
            loading={latestCrawl.isLoading}
            emptyText="No crawls run"
            hint={newest ? `${newest.project_name}` : undefined}
          />
          <StatTile
            label="Resolved issues"
            value={
              issueSummary.data && analysedCrawl && issueSummary.data.resolved_total > 0 ? issueSummary.data.resolved_total : null
            }
            emptyText={analysedCrawl ? "None verified yet" : "Needs two analysed crawls"}
            hint={analysedCrawl ? "Verified by a later crawl" : undefined}
          />
        </div>
      </section>

      {analysedCrawl && issueSummary.data ? (
        <SeverityTiles projectId={analysedCrawl.project_id} counts={issueSummary.data.open_by_severity} />
      ) : null}

      <section aria-labelledby="workspace-heading" className="mb-4">
        <h2 id="workspace-heading" className="mb-3 text-lg font-semibold">
          Workspace
        </h2>
        <Tabs defaultValue="modules">
          <TabsList label="Workspace views">
            <TabsTrigger value="modules">
              <LayoutGrid aria-hidden /> Modules
            </TabsTrigger>
            <TabsTrigger value="trend">
              <TrendingUp aria-hidden /> Score trend
            </TabsTrigger>
            <TabsTrigger value="reports">
              <BarChart3 aria-hidden /> Recent reports
            </TabsTrigger>
          </TabsList>
          <TabsContent value="modules">
            <ModuleTiles />
          </TabsContent>
          <TabsContent value="trend">
            <ScoreTrend crawl={analysedCrawl} timezone={current.timezone} />
          </TabsContent>
          <TabsContent value="reports">
            <RecentReports crawl={analysedCrawl} timezone={current.timezone} />
          </TabsContent>
        </Tabs>
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

const SEVERITY_ORDER: Severity[] = ["critical", "high", "medium", "low"];

function SeverityTiles({ projectId, counts }: { projectId: string; counts: Record<Severity, number> }) {
  return (
    <section aria-labelledby="severity-heading" className="mb-8">
      <h2 id="severity-heading" className="mb-3 text-lg font-semibold">
        Open issues by severity
      </h2>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {SEVERITY_ORDER.map((severity, i) => {
          const style = SEVERITY_STYLE[severity];
          const Icon = style.icon;
          return (
            <Link
              key={severity}
              href={`/issues?project=${projectId}&severity=${severity}`}
              style={{ animationDelay: `${i * 60}ms` }}
              className="group flex items-center gap-3 rounded-xl border bg-card p-4 shadow-sm transition-all animate-fade-up hover:-translate-y-0.5 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <span
                className="flex size-10 items-center justify-center rounded-lg transition-transform group-hover:scale-110"
                style={{ backgroundColor: `color-mix(in oklch, ${style.color} 16%, transparent)` }}
              >
                <Icon className="size-5" style={{ color: style.color }} aria-hidden />
              </span>
              <span>
                <span className="block text-2xl font-semibold tabular-nums">{counts[severity]}</span>
                <span className="block text-xs text-muted-foreground">{style.label} · view issues</span>
              </span>
            </Link>
          );
        })}
      </div>
    </section>
  );
}

function ModuleTiles() {
  return (
    <div className="space-y-6">
      {NAV_GROUPS.filter((g) => g !== "Workspace").map((group) => (
        <div key={group}>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-widest text-muted-foreground">{group}</h3>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {NAV_ITEMS.filter((item) => item.group === group).map((item, i) => (
              <LaunchTile
                key={item.href}
                href={item.href}
                icon={item.icon}
                title={item.label}
                description={item.description}
                style={{ animationDelay: `${i * 50}ms` }}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function ScoreTrend({ crawl, timezone }: { crawl: CrawlJob | null; timezone: string }) {
  const history = useScoreHistory(crawl?.project_id ?? null);
  if (!crawl) return <EmptyState title="No analysed crawl yet" description="The trend starts with the first analysed crawl." />;
  if (history.isLoading) return <LoadingState rows={3} />;
  if (history.error) return <ErrorState error={history.error} onRetry={() => void history.refetch()} />;
  const points = (history.data ?? [])
    .filter((p) => p.overall !== null)
    .map((p) => ({
      label: formatDateTime(p.created_at, timezone),
      tick: new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: timezone }).format(new Date(p.created_at)),
      overall: Math.round(p.overall as number),
    }));
  if (points.length < 2) {
    return (
      <EmptyState
        title="The trend needs two analysed crawls"
        description={
          points.length === 1 ? `One analysed crawl so far, scoring ${points[0].overall}. Crawl again to see the trend.` : "No scored crawls yet."
        }
      />
    );
  }
  const first = points[0].overall;
  const last = points[points.length - 1].overall;
  return (
    <Card>
      <CardHeader>
        <CardTitle>{crawl.project_name}: overall health by crawl</CardTitle>
        <CardDescription>
          From {first} to {last} over {points.length} analysed crawls.{" "}
          <Link href="/monitoring" className="text-primary underline-offset-4 hover:underline">
            Full history and table
          </Link>
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div role="img" aria-label={`Overall health trend for ${crawl.project_name}: ${first} to ${last} across ${points.length} crawls`} className="h-48 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={points} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
              <defs>
                <linearGradient id="overview-trend" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0" stopColor="var(--primary)" stopOpacity={0.35} />
                  <stop offset="1" stopColor="var(--primary)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="tick" tickLine={false} axisLine={false} fontSize={12} stroke="var(--muted-foreground)" />
              <YAxis domain={[0, 100]} tickLine={false} axisLine={false} fontSize={12} stroke="var(--muted-foreground)" width={40} />
              <Tooltip
                cursor={{ stroke: "var(--border)" }}
                contentStyle={{ background: "var(--popover)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12 }}
                labelFormatter={(_, payload) => payload?.[0]?.payload.label ?? ""}
                formatter={(value) => [value, "Overall score"]}
              />
              <Area type="monotone" dataKey="overall" stroke="var(--primary)" strokeWidth={2} fill="url(#overview-trend)" dot={{ r: 3 }} activeDot={{ r: 5 }} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

function RecentReports({ crawl, timezone }: { crawl: CrawlJob | null; timezone: string }) {
  const reports = useReports(crawl?.project_id ?? null);
  if (!crawl) return <EmptyState title="No reports yet" description="Reports can be generated once a crawl has been analysed." />;
  if (reports.isLoading) return <LoadingState rows={3} />;
  if (reports.error) return <ErrorState error={reports.error} onRetry={() => void reports.refetch()} />;
  const items = reports.data?.items.slice(0, 5) ?? [];
  if (items.length === 0) {
    return (
      <EmptyState
        title="No reports for this project yet"
        description="Generate a management report from the Reports page."
        action={
          <Link href="/reports" className="text-sm font-medium text-primary underline-offset-4 hover:underline">
            Go to Reports
          </Link>
        }
      />
    );
  }
  return (
    <ul className="grid gap-3 sm:grid-cols-2">
      {items.map((report, i) => (
        <li key={report.id} className="animate-fade-up" style={{ animationDelay: `${i * 50}ms` }}>
          <Link
            href={`/reports/${report.id}`}
            className="group flex items-center gap-3 rounded-xl border bg-card p-4 shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <span className="flex size-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <BarChart3 className="size-5" aria-hidden />
            </span>
            <span className="min-w-0">
              <span className="block truncate font-medium">{report.title}</span>
              <span className="block text-xs text-muted-foreground">
                {formatDateTime(report.created_at, timezone)} · {report.status}
              </span>
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
