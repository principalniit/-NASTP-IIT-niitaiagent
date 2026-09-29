"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Download, FileText, Loader2, Trash2 } from "lucide-react";
import Link from "next/link";
import { useId, useState } from "react";

import { useAIReady } from "@/components/ai/ai-status";
import { PageHeader } from "@/components/app/page-header";
import { EmptyState, ErrorState, LoadingState } from "@/components/app/states";
import { AnalysisGate } from "@/components/seo/analysis-gate";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, ApiError, downloadFile } from "@/lib/api";
import { useCurrentOrg } from "@/lib/current-org";
import { keys, useReports } from "@/lib/queries";
import type { CrawlJob, Project, Report } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

export function reportFilename(report: Report, extension: string): string {
  const stem = report.title.replace(/[^A-Za-z0-9]+/g, "-").replace(/^-|-$/g, "").toLowerCase().slice(0, 60) || "report";
  return `${stem}-${report.created_at.slice(0, 10)}.${extension}`;
}

export function ReportStatusBadge({ report }: { report: Report }) {
  if (report.status === "queued" || report.status === "running") {
    return (
      <span className="inline-flex items-center gap-1 text-xs">
        <Loader2 className="size-3.5 animate-spin" aria-hidden /> {report.status === "queued" ? "Queued" : "Generating"}
      </span>
    );
  }
  return report.status === "completed" ? <Badge variant="success">Ready</Badge> : <Badge variant="destructive">Failed</Badge>;
}

function GenerateCard({ project, crawl }: { project: Project; crawl: CrawlJob }) {
  const queryClient = useQueryClient();
  const { current } = useCurrentOrg();
  const { ready } = useAIReady();
  const titleId = useId();
  const aiId = useId();
  const [title, setTitle] = useState("");
  const [includeAi, setIncludeAi] = useState(true);
  const generate = useMutation({
    mutationFn: () =>
      api<Report>(`/projects/${project.id}/reports`, {
        method: "POST",
        body: { title: title.trim() || null, include_ai: ready && includeAi },
      }),
    onSuccess: () => {
      setTitle("");
      void queryClient.invalidateQueries({ queryKey: keys.reports(project.id) });
    },
  });
  return (
    <Card className="mb-6">
      <CardHeader>
        <CardTitle>New report</CardTitle>
        <CardDescription>
          From the crawl finished {crawl.finished_at ? formatDateTime(crawl.finished_at, current?.timezone) : "recently"}. The
          report is a snapshot: it does not change when you crawl again.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form
          className="flex flex-col gap-4 md:flex-row md:items-end"
          onSubmit={(e) => {
            e.preventDefault();
            generate.mutate();
          }}
        >
          <div className="flex-1 space-y-1.5">
            <Label htmlFor={titleId}>Title (optional)</Label>
            <Input id={titleId} value={title} maxLength={200} placeholder={`SEO health report: ${project.name}`} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="flex items-center gap-2 md:pb-2">
            <input
              id={aiId}
              type="checkbox"
              className="size-4"
              checked={ready && includeAi}
              disabled={!ready}
              onChange={(e) => setIncludeAi(e.target.checked)}
            />
            <Label htmlFor={aiId} className="font-normal">
              {ready ? "Include AI summary and accepted recommendations" : "AI is off: the report uses crawl data only"}
            </Label>
          </div>
          <Button type="submit" disabled={generate.isPending || (title.trim().length > 0 && title.trim().length < 3)}>
            <FileText aria-hidden /> Generate report
          </Button>
        </form>
        {generate.error ? (
          <Alert variant="destructive" className="mt-4">
            <AlertDescription>{generate.error instanceof ApiError ? generate.error.message : "Could not start the report."}</AlertDescription>
          </Alert>
        ) : null}
      </CardContent>
    </Card>
  );
}

function ReportRow({ report }: { report: Report }) {
  const { current, can } = useCurrentOrg();
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const remove = useMutation({
    mutationFn: () => api(`/reports/${report.id}`, { method: "DELETE" }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: keys.reports(report.project_id) }),
  });
  const done = report.status === "completed";
  return (
    <TableRow>
      <TableCell className="max-w-sm">
        {done ? (
          <Link href={`/reports/${report.id}`} className="font-medium text-primary underline-offset-4 hover:underline">
            {report.title}
          </Link>
        ) : (
          <span className="font-medium">{report.title}</span>
        )}
        <span className="block text-xs text-muted-foreground">{report.include_ai ? "With AI section" : "Crawl data only"}</span>
        {report.error ? <span className="block text-xs text-destructive">{report.error}</span> : null}
      </TableCell>
      <TableCell className="whitespace-nowrap">{formatDateTime(report.created_at, current?.timezone)}</TableCell>
      <TableCell><ReportStatusBadge report={report} /></TableCell>
      <TableCell className="text-right">
        <div className="flex justify-end gap-2">
          {done && report.pdf_status === "ready" ? (
            <Button size="sm" variant="outline" onClick={() => void downloadFile(`/reports/${report.id}/pdf`, reportFilename(report, "pdf"))}>
              <Download aria-hidden /> PDF
            </Button>
          ) : null}
          {can("reports:generate") && (done || report.status === "failed") ? (
            confirming ? (
              <>
                <Button size="sm" variant="destructive" onClick={() => remove.mutate()} disabled={remove.isPending}>Delete</Button>
                <Button size="sm" variant="ghost" onClick={() => setConfirming(false)}>Keep</Button>
              </>
            ) : (
              <Button size="sm" variant="ghost" aria-label={`Delete ${report.title}`} onClick={() => setConfirming(true)}>
                <Trash2 aria-hidden />
              </Button>
            )
          ) : null}
        </div>
      </TableCell>
    </TableRow>
  );
}

function ReportList({ project }: { project: Project }) {
  const reports = useReports(project.id);
  if (reports.isLoading) return <LoadingState rows={3} />;
  if (reports.error) return <ErrorState error={reports.error} onRetry={() => void reports.refetch()} />;
  if (!reports.data?.items.length) {
    return <EmptyState title="No reports yet" description="Generate a report to share the audit with management." />;
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Report</TableHead>
          <TableHead>Created</TableHead>
          <TableHead>Status</TableHead>
          <TableHead className="text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {reports.data.items.map((r) => <ReportRow key={r.id} report={r} />)}
      </TableBody>
    </Table>
  );
}

export function ReportsView() {
  const { can } = useCurrentOrg();
  return (
    <AnalysisGate
      header={(picker) => (
        <PageHeader
          title="Reports"
          description="Management reports built from the latest analysed crawl, with evidence, an action plan and the methodology."
          actions={picker}
        />
      )}
    >
      {({ project, crawl }) => (
        <>
          {can("reports:generate") ? <GenerateCard project={project} crawl={crawl} /> : null}
          <ReportList project={project} />
        </>
      )}
    </AnalysisGate>
  );
}
