"use client";

import { Sparkles } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { AIStatusNotice, useAIReady, useRequestAnalysis } from "@/components/ai/ai-status";
import { AnalysisCard } from "@/components/ai/analysis-result";
import { PageHeader } from "@/components/app/page-header";
import { EmptyState, ErrorState, LoadingState } from "@/components/app/states";
import { AnalysisGate } from "@/components/seo/analysis-gate";
import { SeverityBadge } from "@/components/seo/severity";
import { DraftTable } from "@/components/views/approvals-view";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ApiError } from "@/lib/api";
import { useCurrentOrg } from "@/lib/current-org";
import { useDrafts, useIssues } from "@/lib/queries";
import type { Issue, Project } from "@/lib/types";
import { pathOf } from "@/lib/utils";

function Opportunities({ project }: { project: Project }) {
  const { can } = useCurrentOrg();
  const { ready } = useAIReady();
  const issues = useIssues(project.id, { category: "content", page_size: 50 });
  const request = useRequestAnalysis(project.id);
  const [active, setActive] = useState<string | null>(null);
  const canDraft = can("drafts:create");

  if (issues.isLoading) return <LoadingState rows={4} />;
  if (issues.error) return <ErrorState error={issues.error} onRetry={() => void issues.refetch()} />;
  const items = issues.data?.items ?? [];
  if (!items.length) {
    return <EmptyState title="No open content issues" description="The latest analysed crawl found no thin, duplicate or overlapping content." />;
  }
  const draft = (issue: Issue) =>
    request.mutate({ kind: "content_outline", page_url: issue.affected_url ?? "" }, { onSuccess: (a) => setActive(a.id) });
  return (
    <div className="space-y-4">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-28">Severity</TableHead>
            <TableHead>Opportunity</TableHead>
            <TableHead className="hidden md:table-cell">Page</TableHead>
            {canDraft ? <TableHead className="text-right">Draft</TableHead> : null}
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((issue) => (
            <TableRow key={issue.id}>
              <TableCell><SeverityBadge severity={issue.severity} /></TableCell>
              <TableCell className="max-w-md">
                <Link href={`/issues/${issue.id}`} className="font-medium text-primary underline-offset-4 hover:underline">{issue.title}</Link>
                <span className="block text-xs text-muted-foreground">{issue.recommendation}</span>
              </TableCell>
              <TableCell className="hidden max-w-60 truncate text-muted-foreground md:table-cell" title={issue.affected_url ?? undefined}>
                {issue.affected_url ? pathOf(issue.affected_url) : `${issue.affected_page_count} pages`}
              </TableCell>
              {canDraft ? (
                <TableCell className="text-right">
                  {issue.scope === "page" && issue.affected_url ? (
                    <Button size="sm" variant="outline" disabled={!ready || request.isPending} onClick={() => draft(issue)}>
                      <Sparkles aria-hidden /> Draft outline
                    </Button>
                  ) : (
                    <span className="text-xs text-muted-foreground">Open the issue to see each page</span>
                  )}
                </TableCell>
              ) : null}
            </TableRow>
          ))}
        </TableBody>
      </Table>
      {request.error ? (
        <Alert variant="destructive">
          <AlertDescription>{request.error instanceof ApiError ? request.error.message : "Could not start the draft."}</AlertDescription>
        </Alert>
      ) : null}
      {active ? <AnalysisCard id={active} /> : null}
    </div>
  );
}

function ContentDrafts({ project }: { project: Project }) {
  const drafts = useDrafts(project.id, {});
  const content = (drafts.data?.items ?? []).filter((d) => d.field === "content_outline" || d.field === "content_section");
  if (!content.length) return null;
  return (
    <div className="space-y-3">
      <h2 className="text-lg font-semibold">Recent content drafts</h2>
      <DraftTable drafts={content} />
    </div>
  );
}

export function ContentView() {
  return (
    <AnalysisGate
      header={(picker) => (
        <PageHeader
          title="Content Opportunities"
          description="Thin, duplicate and overlapping content from the latest analysis. Outlines are drafts for editors, and facts to confirm are marked [verify]."
          actions={picker}
        />
      )}
    >
      {({ project }) => (
        <>
          <AIStatusNotice />
          <div className="space-y-8">
            <Opportunities project={project} />
            <ContentDrafts project={project} />
          </div>
        </>
      )}
    </AnalysisGate>
  );
}
