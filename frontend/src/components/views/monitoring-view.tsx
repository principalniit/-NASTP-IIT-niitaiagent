"use client";

import Link from "next/link";
import { useState } from "react";
import { CartesianGrid, LabelList, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { PageHeader } from "@/components/app/page-header";
import { EmptyState, ErrorState, LoadingState } from "@/components/app/states";
import { AnalysisGate } from "@/components/seo/analysis-gate";
import { SeverityBadge } from "@/components/seo/severity";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { NativeSelect } from "@/components/ui/native-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError } from "@/lib/api";
import { useCurrentOrg } from "@/lib/current-org";
import { useComparison, useCrawls, useScoreHistory } from "@/lib/queries";
import type { Capped, ComparedIssue, Comparison, Project, ScorePoint } from "@/lib/types";
import { formatDateTime, pathOf } from "@/lib/utils";

const CATEGORIES: [keyof ScorePoint, string][] = [
  ["technical", "Technical"],
  ["on_page", "On-page"],
  ["content", "Content"],
  ["internal_linking", "Internal linking"],
  ["structured_data", "Structured data"],
];

const shortDate = (value: string, timeZone?: string, withTime = false) =>
  new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
    timeZone,
  }).format(new Date(value));
const scoreText = (value: number | null | undefined) => (value === null || value === undefined ? "—" : Math.round(value).toString());

function ChartTooltip({ active, payload }: { active?: boolean; payload?: { payload: ScorePoint & { label: string } }[] }) {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  return (
    <div className="rounded-md border bg-popover px-3 py-2 text-xs shadow-sm">
      <p className="font-medium">{point.label}</p>
      <p className="mt-1 flex items-center gap-2">
        <span className="inline-block h-0.5 w-3 bg-primary" aria-hidden />
        Overall score <span className="ml-auto font-semibold tabular-nums">{scoreText(point.overall)}</span>
      </p>
    </div>
  );
}

function ScoreHistory({ project }: { project: Project }) {
  const { current } = useCurrentOrg();
  const history = useScoreHistory(project.id);
  const tz = current?.timezone;
  if (history.isLoading) return <LoadingState rows={4} />;
  if (history.error) return <ErrorState error={history.error} onRetry={() => void history.refetch()} />;
  const raw = history.data ?? [];
  // Show the time too when two crawls fall on the same day, so every tick is distinct.
  const days = raw.map((p) => shortDate(p.created_at, tz));
  const withTime = new Set(days).size < days.length;
  const points = raw.map((p) => ({ ...p, label: formatDateTime(p.created_at, tz), tick: shortDate(p.created_at, tz, withTime) }));
  const lastIndex = points.length - 1;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Overall site-health score by crawl</CardTitle>
        <CardDescription>
          One point per analysed crawl, out of 100. A health indicator for prioritising work, not a search ranking.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {points.length < 2 ? (
          <p className="text-sm text-muted-foreground">
            {points.length === 1
              ? `One analysed crawl so far (score ${scoreText(points[0].overall)}). The trend appears after the next crawl.`
              : "No analysed crawls yet."}
          </p>
        ) : (
          <div role="img" aria-label={`Overall score over ${points.length} crawls, from ${scoreText(points[0].overall)} to ${scoreText(points[points.length - 1].overall)}`} className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={points} margin={{ top: 20, right: 16, bottom: 0, left: -12 }}>
                <CartesianGrid vertical={false} stroke="var(--border)" strokeWidth={1} />
                <XAxis dataKey="tick" tickLine={false} axisLine={{ stroke: "var(--border)" }} tick={{ fill: "var(--muted-foreground)", fontSize: 12 }} />
                <YAxis domain={[0, 100]} ticks={[0, 25, 50, 75, 100]} tickLine={false} axisLine={false} tick={{ fill: "var(--muted-foreground)", fontSize: 12 }} />
                <Tooltip content={<ChartTooltip />} cursor={{ stroke: "var(--muted-foreground)", strokeWidth: 1 }} />
                <Line
                  type="linear"
                  dataKey="overall"
                  stroke="var(--primary)"
                  strokeWidth={2}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  connectNulls
                  dot={{ r: 4, fill: "var(--primary)", stroke: "var(--background)", strokeWidth: 2 }}
                  activeDot={{ r: 6, fill: "var(--primary)", stroke: "var(--background)", strokeWidth: 2 }}
                  isAnimationActive={false}
                >
                  <LabelList
                    dataKey="overall"
                    content={({ index, x, y, value }) =>
                      index === lastIndex && typeof x === "number" && typeof y === "number" && value !== undefined ? (
                        <text x={x} y={y - 12} textAnchor="end" fontSize={12} fontWeight={600} fill="var(--foreground)">
                          {Math.round(Number(value))}
                        </text>
                      ) : null
                    }
                  />
                </Line>
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
        {points.length ? (
          <details>
            <summary className="cursor-pointer text-sm font-medium">Scores as a table</summary>
            <Table className="mt-2">
              <TableHeader>
                <TableRow>
                  <TableHead>Crawl</TableHead>
                  <TableHead className="text-right">Overall</TableHead>
                  {CATEGORIES.map(([, label]) => <TableHead key={label} className="text-right">{label}</TableHead>)}
                </TableRow>
              </TableHeader>
              <TableBody>
                {[...points].reverse().map((p) => (
                  <TableRow key={p.crawl_job_id}>
                    <TableCell className="whitespace-nowrap">{p.label}</TableCell>
                    <TableCell className="text-right font-medium tabular-nums">{scoreText(p.overall)}</TableCell>
                    {CATEGORIES.map(([key, label]) => (
                      <TableCell key={label} className="text-right tabular-nums">{scoreText(p[key] as number | null)}</TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </details>
        ) : null}
      </CardContent>
    </Card>
  );
}

function IssueList({ title, list, empty }: { title: string; list: Capped<ComparedIssue>; empty: string }) {
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold">
        {title} <span className="font-normal text-muted-foreground">({list.count})</span>
      </h3>
      {list.items.length ? (
        <ul className="space-y-1.5 text-sm">
          {list.items.map((i) => (
            <li key={i.id} className="flex items-start gap-2">
              <SeverityBadge severity={i.severity} />
              <Link href={`/issues/${i.id}`} className="text-primary underline-offset-4 hover:underline">{i.title}</Link>
            </li>
          ))}
          {list.count > list.items.length ? <li className="text-xs text-muted-foreground">and {list.count - list.items.length} more</li> : null}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">{empty}</p>
      )}
    </div>
  );
}

function PageChanges({ comparison }: { comparison: Comparison }) {
  const p = comparison.pages;
  const value = (v: unknown) => (v === null || v === undefined || v === "" ? "none" : String(v));
  const groups: { title: string; count: number; rows: { url: string; detail?: string }[] }[] = [
    { title: "Pages added", count: p.added.count, rows: p.added.items.map((url) => ({ url })) },
    { title: "Pages no longer found", count: p.removed.count, rows: p.removed.items.map((url) => ({ url })) },
    { title: "Status code changes", count: p.status_changes.count, rows: p.status_changes.items.map((c) => ({ url: c.url, detail: `${value(c.from)} → ${value(c.to)}` })) },
    { title: "Title changes", count: p.title_changes.count, rows: p.title_changes.items.map((c) => ({ url: c.url, detail: `“${value(c.from)}” → “${value(c.to)}”` })) },
    { title: "Meta description changes", count: p.meta_description_changes.count, rows: p.meta_description_changes.items.map((c) => ({ url: c.url, detail: `“${value(c.from)}” → “${value(c.to)}”` })) },
    { title: "Redirect changes", count: p.redirect_changes.count, rows: p.redirect_changes.items.map((c) => ({ url: c.url, detail: `${value(c.from)} → ${value(c.to)}` })) },
    { title: "Content changes", count: p.content_changed.count, rows: p.content_changed.items.map((url) => ({ url })) },
    { title: "Internal links pointing here", count: p.inbound_link_changes.count, rows: p.inbound_link_changes.items.map((c) => ({ url: c.url, detail: `${c.from} → ${c.to}` })) },
  ];
  return (
    <div className="divide-y rounded-lg border">
      {groups.map((g) => (
        <details key={g.title} className="px-4 py-2" open={false}>
          <summary className="flex cursor-pointer items-center justify-between text-sm">
            <span className="font-medium">{g.title}</span>
            <span className="tabular-nums text-muted-foreground">{g.count}</span>
          </summary>
          {g.rows.length ? (
            <ul className="mt-2 space-y-1 text-sm">
              {g.rows.map((r) => (
                <li key={r.url + (r.detail ?? "")}>
                  <span className="break-all font-mono text-xs">{pathOf(r.url)}</span>
                  {r.detail ? <span className="block text-xs text-muted-foreground">{r.detail}</span> : null}
                </li>
              ))}
              {g.count > g.rows.length ? <li className="text-xs text-muted-foreground">and {g.count - g.rows.length} more</li> : null}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-muted-foreground">No changes.</p>
          )}
        </details>
      ))}
    </div>
  );
}

function CrawlComparison({ project }: { project: Project }) {
  const { current } = useCurrentOrg();
  const tz = current?.timezone;
  const crawls = useCrawls(current?.id ?? null, { project_id: project.id, analysed: true, page_size: 20 });
  const items = crawls.data?.items ?? [];
  const [toId, setToId] = useState("");
  const [fromId, setFromId] = useState("");
  const to = toId || items[0]?.id;
  const toIndex = items.findIndex((c) => c.id === to);
  const earlier = items.slice(toIndex + 1);
  const from = earlier.some((c) => c.id === fromId) ? fromId : earlier[0]?.id;
  const comparison = useComparison(project.id, from, to, !!from && !!to);

  if (crawls.isLoading) return <LoadingState rows={4} />;
  if (items.length < 2) {
    return <EmptyState title="Nothing to compare yet" description="Comparisons appear once the project has two analysed crawls." />;
  }
  const label = (id: string) => {
    const c = items.find((x) => x.id === id);
    return c?.finished_at ? formatDateTime(c.finished_at, tz) : "crawl";
  };
  const c = comparison.data;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Compare two crawls</CardTitle>
        <CardDescription>An issue counts as resolved only when the later crawl re-examined the pages it concerned.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="flex flex-wrap items-end gap-4">
          <div className="space-y-1.5">
            <label htmlFor="compare-from" className="text-sm font-medium">Earlier crawl</label>
            <NativeSelect id="compare-from" className="w-64" value={from ?? ""} onChange={(e) => setFromId(e.target.value)}>
              {earlier.map((x) => <option key={x.id} value={x.id}>{label(x.id)}</option>)}
            </NativeSelect>
          </div>
          <div className="space-y-1.5">
            <label htmlFor="compare-to" className="text-sm font-medium">Later crawl</label>
            <NativeSelect id="compare-to" className="w-64" value={to ?? ""} onChange={(e) => { setToId(e.target.value); setFromId(""); }}>
              {items.slice(0, -1).map((x) => <option key={x.id} value={x.id}>{label(x.id)}</option>)}
            </NativeSelect>
          </div>
        </div>
        {comparison.isLoading ? (
          <LoadingState rows={4} />
        ) : comparison.error ? (
          comparison.error instanceof ApiError ? <p className="text-sm text-muted-foreground">{comparison.error.message}</p> : <ErrorState error={comparison.error} />
        ) : c ? (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Score</TableHead>
                  <TableHead className="text-right">Earlier</TableHead>
                  <TableHead className="text-right">Later</TableHead>
                  <TableHead className="text-right">Change</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {[["overall", "Overall"], ...CATEGORIES].map(([key, name]) => {
                  const s = c.score_change[key as string];
                  return (
                    <TableRow key={key as string}>
                      <TableCell className={key === "overall" ? "font-medium" : ""}>{name as string}</TableCell>
                      <TableCell className="text-right tabular-nums">{scoreText(s?.from)}</TableCell>
                      <TableCell className="text-right tabular-nums">{scoreText(s?.to)}</TableCell>
                      <TableCell className="text-right tabular-nums">
                        {s?.change === null || s?.change === undefined ? "—" : `${s.change > 0 ? "+" : ""}${s.change.toFixed(0)}`}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
            <div className="grid gap-6 md:grid-cols-3">
              <IssueList title="New issues" list={c.issues.new} empty="No new issues." />
              <IssueList title="Resolved (verified)" list={c.issues.resolved} empty="None resolved." />
              <IssueList title="Came back" list={c.issues.recurring} empty="No recurring issues." />
            </div>
            <div className="space-y-2">
              <h3 className="text-sm font-semibold">
                Page changes <span className="font-normal text-muted-foreground">({c.from_crawl.pages} → {c.to_crawl.pages} pages)</span>
              </h3>
              <PageChanges comparison={c} />
            </div>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function MonitoringView() {
  return (
    <AnalysisGate
      header={(picker) => (
        <PageHeader title="Monitoring" description="How the site changes from crawl to crawl." actions={picker} />
      )}
    >
      {({ project }) => (
        <div className="space-y-6">
          <ScoreHistory project={project} />
          <CrawlComparison project={project} />
        </div>
      )}
    </AnalysisGate>
  );
}
