"use client";

import Link from "next/link";

import { EmptyState, ErrorState, LoadingState } from "@/components/app/states";
import { ProjectPicker, useProjectChoice } from "@/components/seo/project-picker";
import { useCurrentOrg } from "@/lib/current-org";
import { useCrawls, useLatestAnalysedCrawl } from "@/lib/queries";
import type { CrawlJob, Organisation, Project } from "@/lib/types";

export interface AnalysedContext {
  org: Organisation;
  project: Project;
  crawl: CrawlJob;
}

/** Resolves organisation, project and latest analysed crawl, with honest empty states. */
export function AnalysisGate({
  header,
  children,
}: {
  header: (picker: React.ReactNode) => React.ReactNode;
  children: (ctx: AnalysedContext) => React.ReactNode;
}) {
  const { current } = useCurrentOrg();
  const choice = useProjectChoice(current?.id ?? null);
  const latest = useLatestAnalysedCrawl(current?.id ?? null, choice.project?.id ?? null);
  const newest = useCrawls(current?.id ?? null, { project_id: choice.project?.id, page_size: 1 }, !!choice.project);
  const picker = <ProjectPicker projects={choice.projects} project={choice.project} onChange={choice.choose} />;

  if (!current || choice.isLoading) return <LoadingState rows={4} />;
  if (!choice.project) {
    return (
      <>
        {header(null)}
        <EmptyState title="No projects yet" description="Add a project and crawl it to see SEO results." />
      </>
    );
  }
  let body: React.ReactNode;
  if (latest.isLoading || newest.isLoading) {
    body = <LoadingState rows={4} />;
  } else if (latest.error) {
    body = <ErrorState error={latest.error} onRetry={() => void latest.refetch()} />;
  } else if (latest.crawl) {
    body = children({ org: current, project: choice.project, crawl: latest.crawl });
  } else {
    const job = newest.data?.items[0];
    const message = !job
      ? "This project has not been crawled yet. Results appear after a crawl is analysed."
      : job.analysis_status === "queued" || job.analysis_status === "running"
        ? "The latest crawl is being analysed. This page updates when the analysis finishes."
        : job.analysis_status === "failed"
          ? `The analysis of the latest crawl failed: ${job.analysis_error ?? "unknown error"}`
          : job.status === "completed"
            ? "The latest crawl has not been analysed."
            : "Results appear once a crawl completes and is analysed.";
    body = (
      <EmptyState
        title="No analysis results yet"
        description={message}
        action={
          <Link href={job ? `/crawls/${job.id}` : "/crawls"} className="text-sm font-medium text-primary underline-offset-4 hover:underline">
            {job ? "View the latest crawl" : "Go to Crawl Explorer"}
          </Link>
        }
      />
    );
  }
  return (
    <>
      {header(picker)}
      {body}
    </>
  );
}
