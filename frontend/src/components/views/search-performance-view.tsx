"use client";

import { ArrowUpNarrowWide, Eye, MousePointerClick, Percent } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { PageHeader } from "@/components/app/page-header";
import { EmptyState, ErrorState, LoadingState } from "@/components/app/states";
import { StatTile } from "@/components/app/stat-tile";
import { ProjectPicker, useProjectChoice } from "@/components/seo/project-picker";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { NativeSelect } from "@/components/ui/native-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useCurrentOrg } from "@/lib/current-org";
import { useSearchPerformance } from "@/lib/queries";
import type { SearchPerformance, SearchRow } from "@/lib/types";
import { ctrText, formatDateTime, pathOf, positionText } from "@/lib/utils";

const count = (n: number) => n.toLocaleString("en");
const day = (iso: string) => new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: "UTC" }).format(new Date(iso));

function DailyChart({ data, metric, label }: { data: SearchPerformance["daily"]; metric: "clicks" | "impressions"; label: string }) {
  const points = data.map((d) => ({ ...d, tick: day(d.day) }));
  const values = points.map((p) => p[metric]);
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">{label} per day</CardTitle>
        <CardDescription>From Google Search only.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        <div
          role="img"
          aria-label={`${label} per day over ${points.length} days, from ${count(values[0] ?? 0)} to ${count(values[values.length - 1] ?? 0)}`}
          className="h-48 w-full"
        >
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={points} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
              <CartesianGrid vertical={false} stroke="var(--border)" strokeWidth={1} />
              <XAxis dataKey="tick" tickLine={false} axisLine={{ stroke: "var(--border)" }} minTickGap={24} tick={{ fill: "var(--muted-foreground)", fontSize: 12 }} />
              <YAxis allowDecimals={false} tickLine={false} axisLine={false} width={48} tick={{ fill: "var(--muted-foreground)", fontSize: 12 }} />
              <Tooltip
                cursor={{ stroke: "var(--muted-foreground)", strokeWidth: 1 }}
                content={({ active, payload }) => {
                  const p = payload?.[0]?.payload as (typeof points)[number] | undefined;
                  return active && p ? (
                    <div className="rounded-md border bg-popover px-3 py-2 text-xs shadow-sm">
                      <p className="font-medium">{p.tick}</p>
                      <p className="mt-1 tabular-nums">
                        {label}: <span className="font-semibold">{count(p[metric])}</span>
                      </p>
                    </div>
                  ) : null;
                }}
              />
              <Line type="linear" dataKey={metric} stroke="var(--primary)" strokeWidth={2} dot={false} activeDot={{ r: 5, stroke: "var(--background)", strokeWidth: 2 }} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <details>
          <summary className="cursor-pointer text-sm font-medium">{label} as a table</summary>
          <Table className="mt-2">
            <TableHeader>
              <TableRow>
                <TableHead>Day</TableHead>
                <TableHead className="text-right">{label}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {points.map((p) => (
                <TableRow key={p.day}>
                  <TableCell>{p.tick}</TableCell>
                  <TableCell className="text-right tabular-nums">{count(p[metric])}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </details>
      </CardContent>
    </Card>
  );
}

function RowsTable<T extends SearchRow>({ rows, first, label, render }: { rows: T[]; first: string; label: string; render: (row: T) => React.ReactNode }) {
  return (
    <Table aria-label={label}>
      <TableHeader>
        <TableRow>
          <TableHead>{first}</TableHead>
          <TableHead className="text-right">Clicks</TableHead>
          <TableHead className="hidden text-right sm:table-cell">Impressions</TableHead>
          <TableHead className="hidden text-right md:table-cell">CTR</TableHead>
          <TableHead className="text-right">Position</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((r, i) => (
          <TableRow key={i}>
            <TableCell className="max-w-[18rem] truncate font-medium">{render(r)}</TableCell>
            <TableCell className="text-right tabular-nums">{count(r.clicks)}</TableCell>
            <TableCell className="hidden text-right tabular-nums sm:table-cell">{count(r.impressions)}</TableCell>
            <TableCell className="hidden text-right tabular-nums md:table-cell">{ctrText(r.ctr)}</TableCell>
            <TableCell className="text-right tabular-nums">{positionText(r.position)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function Performance({ data }: { data: SearchPerformance }) {
  const { current } = useCurrentOrg();
  const t = data.totals!;
  return (
    <div className="space-y-6">
      <p className="text-sm text-muted-foreground">
        Google Search Console figures for {data.start ? day(data.start) : ""} to {data.end ? day(data.end) : ""}
        {data.last_synced_at ? `, last imported ${formatDateTime(data.last_synced_at, current?.timezone)}` : ""}. Clicks
        come from Google Search only, not from all visitors. Position is Google&apos;s average position weighted by
        impressions; 1 is the top.
      </p>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile label="Clicks" value={count(t.clicks)} icon={MousePointerClick} />
        <StatTile label="Impressions" value={count(t.impressions)} icon={Eye} />
        <StatTile label="Click-through rate" value={t.ctr === null ? null : ctrText(t.ctr)} emptyText="No impressions" icon={Percent} />
        <StatTile label="Average position" value={t.position === null ? null : positionText(t.position)} emptyText="No impressions" icon={ArrowUpNarrowWide} />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <DailyChart data={data.daily} metric="clicks" label="Clicks" />
        <DailyChart data={data.daily} metric="impressions" label="Impressions" />
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Top pages</CardTitle>
            <CardDescription>By clicks, then impressions.</CardDescription>
          </CardHeader>
          <CardContent>
            {data.top_pages.length ? (
              <RowsTable rows={data.top_pages} first="Page" label="Top pages" render={(r) => <span title={r.page}>{pathOf(r.page)}</span>} />
            ) : (
              <p className="text-sm text-muted-foreground">No pages had impressions in this period.</p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Top search queries</CardTitle>
            <CardDescription>What people searched for when they saw these pages. Google withholds rare queries.</CardDescription>
          </CardHeader>
          <CardContent>
            {data.top_queries.length ? (
              <RowsTable rows={data.top_queries} first="Query" label="Top search queries" render={(r) => r.query} />
            ) : (
              <p className="text-sm text-muted-foreground">Google reported no queries for this period.</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export function SearchPerformanceView() {
  const { current, can } = useCurrentOrg();
  const choice = useProjectChoice(current?.id ?? null);
  const [days, setDays] = useState(28);
  const perf = useSearchPerformance(choice.project?.id ?? null, days);
  const actions = (
    <div className="flex flex-wrap items-center gap-2">
      <ProjectPicker projects={choice.projects} project={choice.project} onChange={choice.choose} />
      <label htmlFor="search-days" className="sr-only">
        Period
      </label>
      <NativeSelect id="search-days" className="h-9 w-36" value={days} onChange={(e) => setDays(Number(e.target.value))}>
        <option value={7}>Last 7 days</option>
        <option value={28}>Last 28 days</option>
        <option value={90}>Last 90 days</option>
      </NativeSelect>
    </div>
  );
  const header = <PageHeader title="Search Performance" description="Clicks, impressions and positions from your own Google Search Console." actions={actions} />;
  if (!current || choice.isLoading) return <LoadingState rows={4} />;
  if (!choice.project) {
    return (
      <>
        {header}
        <EmptyState title="No projects yet" description="Add a project to see its search performance." />
      </>
    );
  }
  let body: React.ReactNode;
  if (perf.isLoading) body = <LoadingState rows={4} />;
  else if (perf.error) body = <ErrorState error={perf.error} onRetry={() => void perf.refetch()} />;
  else if (perf.data?.state === "ready") body = <Performance data={perf.data} />;
  else if (perf.data?.state === "no_data") {
    body = (
      <EmptyState
        title="No search data for this site yet"
        description={`Search Console is connected (${perf.data.properties.join(", ")}), but nothing has been imported for ${choice.project.domain}. Run a sync on the Integrations page, and check that the property covers this site.`}
        action={can("integrations:manage") ? <Button asChild size="sm" variant="outline"><Link href="/integrations">Open Integrations</Link></Button> : undefined}
      />
    );
  } else {
    body = (
      <EmptyState
        title="Search Console is not connected"
        description="Clicks, impressions and positions appear here once an owner or administrator connects your own Google Search Console property. It is free and read-only. Until then, no figures are shown."
        action={can("integrations:manage") ? <Button asChild size="sm" variant="outline"><Link href="/integrations">Connect Search Console</Link></Button> : undefined}
      />
    );
  }
  return (
    <>
      {header}
      {body}
    </>
  );
}
