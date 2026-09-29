"use client";

import Link from "next/link";
import { useState } from "react";

import { NoOrganisation } from "@/components/app/no-organisation";
import { PageHeader } from "@/components/app/page-header";
import { EmptyState, ErrorState, LoadingState } from "@/components/app/states";
import { CrawlProgress, CrawlStatusBadge } from "@/components/crawls/crawl-status";
import { StartCrawlButton } from "@/components/crawls/start-crawl";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { NativeSelect } from "@/components/ui/native-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useCurrentOrg } from "@/lib/current-org";
import { isActiveCrawl, useCrawls, useProjects } from "@/lib/queries";
import { formatDateTime, formatDuration } from "@/lib/utils";

export function CrawlsView() {
  const { current, can, isLoading } = useCurrentOrg();
  const [projectId, setProjectId] = useState("");
  const projects = useProjects(current?.id ?? null, { sort: "name", order: "asc" });
  const crawls = useCrawls(current?.id ?? null, { project_id: projectId || undefined });

  if (isLoading) return <LoadingState />;
  if (!current) return <NoOrganisation />;

  const projectList = projects.data?.items ?? [];
  const selected = projectList.find((p) => p.id === projectId) ?? (projectList.length === 1 ? projectList[0] : undefined);
  const active = crawls.data?.items.filter((job) => isActiveCrawl(job)) ?? [];
  const selectedBusy = !!selected && active.some((job) => job.project_id === selected.id);

  return (
    <>
      <PageHeader
        title="Crawl Explorer"
        description="Crawl a project's website within its limits, then inspect every page found."
      />
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Project</CardTitle>
            <CardDescription>
              Crawls respect robots.txt, the project&apos;s page and depth limits and the delay between requests.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {projects.isLoading ? (
              <LoadingState rows={1} />
            ) : projectList.length === 0 ? (
              <EmptyState title="No projects yet" description="Add a project before starting a crawl." />
            ) : (
              <>
                <div className="max-w-md space-y-1.5">
                  <label htmlFor="crawl-project" className="text-sm font-medium">
                    Project
                  </label>
                  <NativeSelect id="crawl-project" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
                    <option value="">All projects</option>
                    {projectList.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name} ({p.domain})
                      </option>
                    ))}
                  </NativeSelect>
                </div>
                {can("crawls:start") ? (
                  selected ? (
                    <StartCrawlButton
                      key={selected.id}
                      projectId={selected.id}
                      organisationId={current.id}
                      disabled={selectedBusy}
                    />
                  ) : (
                    <p className="text-sm text-muted-foreground">Choose a project to start a crawl.</p>
                  )
                ) : (
                  <p className="text-sm text-muted-foreground">Your role can view crawls but not start them.</p>
                )}
                {selectedBusy ? (
                  <p className="text-sm text-muted-foreground">This project already has a crawl in progress.</p>
                ) : null}
              </>
            )}
          </CardContent>
        </Card>

        {active.length > 0 ? (
          <Card>
            <CardHeader>
              <CardTitle>In progress</CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              {active.map((job) => (
                <div key={job.id} className="space-y-2">
                  <div className="flex items-center gap-2">
                    <Link href={`/crawls/${job.id}`} className="font-medium text-primary underline-offset-4 hover:underline">
                      {job.project_name}
                    </Link>
                    <CrawlStatusBadge status={job.status} />
                  </div>
                  <CrawlProgress job={job} />
                </div>
              ))}
            </CardContent>
          </Card>
        ) : null}

        <Card>
          <CardHeader>
            <CardTitle>Crawl history</CardTitle>
          </CardHeader>
          <CardContent>
            {crawls.isLoading ? (
              <LoadingState />
            ) : crawls.error ? (
              <ErrorState error={crawls.error} onRetry={() => void crawls.refetch()} />
            ) : !crawls.data?.items.length ? (
              <EmptyState title="No crawls yet" description="Crawl results appear here once a crawl has run." />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Project</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="hidden md:table-cell">Started</TableHead>
                    <TableHead className="text-right">Pages</TableHead>
                    <TableHead className="hidden sm:table-cell text-right">Duration</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {crawls.data.items.map((job) => (
                    <TableRow key={job.id}>
                      <TableCell>
                        <Link href={`/crawls/${job.id}`} className="font-medium text-primary underline-offset-4 hover:underline">
                          {job.project_name}
                        </Link>
                        {job.incremental ? <span className="ml-2 text-xs text-muted-foreground">incremental</span> : null}
                      </TableCell>
                      <TableCell>
                        <CrawlStatusBadge status={job.status} />
                      </TableCell>
                      <TableCell className="hidden text-muted-foreground md:table-cell">
                        {formatDateTime(job.started_at ?? job.created_at, current.timezone)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{job.pages_discovered}</TableCell>
                      <TableCell className="hidden text-right tabular-nums sm:table-cell">
                        {formatDuration(job.started_at, job.finished_at)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>
    </>
  );
}
