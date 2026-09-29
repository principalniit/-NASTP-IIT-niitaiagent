"use client";

import Link from "next/link";
import { useState } from "react";

import { NoOrganisation } from "@/components/app/no-organisation";
import { PageHeader } from "@/components/app/page-header";
import { EmptyState, LoadingState } from "@/components/app/states";
import { PagesTable } from "@/components/crawls/pages-table";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { NativeSelect } from "@/components/ui/native-select";
import { useCurrentOrg } from "@/lib/current-org";
import { useCrawls, useProjects } from "@/lib/queries";
import { formatDateTime } from "@/lib/utils";

export function PagesView() {
  const { current, isLoading } = useCurrentOrg();
  const projects = useProjects(current?.id ?? null, { sort: "name", order: "asc" });
  const [chosen, setChosen] = useState("");
  const projectList = projects.data?.items ?? [];
  const projectId = chosen || projectList[0]?.id || "";
  const latest = useCrawls(current?.id ?? null, { project_id: projectId, status: "completed", page_size: 1 }, !!projectId);

  if (isLoading || projects.isLoading) return <LoadingState />;
  if (!current) return <NoOrganisation />;
  if (projectList.length === 0) {
    return (
      <>
        <PageHeader title="Pages" />
        <EmptyState title="No projects yet" description="Add a project and crawl it to see its pages." />
      </>
    );
  }
  const crawl = latest.data?.items[0];

  return (
    <>
      <PageHeader title="Pages" description="Pages from the most recent completed crawl of a project." />
      <div className="mb-4 max-w-md space-y-1.5">
        <label htmlFor="pages-project" className="text-sm font-medium">
          Project
        </label>
        <NativeSelect id="pages-project" value={projectId} onChange={(e) => setChosen(e.target.value)}>
          {projectList.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} ({p.domain})
            </option>
          ))}
        </NativeSelect>
      </div>
      {latest.isLoading ? (
        <LoadingState />
      ) : !crawl ? (
        <EmptyState
          title="No completed crawl for this project"
          description="Pages appear here after a crawl finishes."
          action={
            <Link href="/crawls" className="text-sm font-medium text-primary underline-offset-4 hover:underline">
              Go to Crawl Explorer
            </Link>
          }
        />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>{crawl.project_name}</CardTitle>
            <CardDescription>
              Crawl finished {crawl.finished_at ? formatDateTime(crawl.finished_at, current.timezone) : ""} ·{" "}
              <Link href={`/crawls/${crawl.id}`} className="text-primary underline-offset-4 hover:underline">
                view crawl summary
              </Link>
            </CardDescription>
          </CardHeader>
          <CardContent>
            <PagesTable crawlId={crawl.id} version={crawl.id} />
          </CardContent>
        </Card>
      )}
    </>
  );
}
