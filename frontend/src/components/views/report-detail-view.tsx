"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Download } from "lucide-react";
import Link from "next/link";

import { PageHeader } from "@/components/app/page-header";
import { EmptyState, ErrorState, LoadingState } from "@/components/app/states";
import { reportFilename, ReportStatusBadge } from "@/components/views/reports-view";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { api, ApiError, apiText, downloadFile } from "@/lib/api";
import { useCurrentOrg } from "@/lib/current-org";
import type { Report } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

export function ReportDetailView({ reportId }: { reportId: string }) {
  const { current } = useCurrentOrg();
  const report = useQuery({
    queryKey: ["reports", reportId],
    queryFn: () => api<Report>(`/reports/${reportId}`),
    refetchInterval: (query) => (["queued", "running"].includes(query.state.data?.status ?? "") ? 2000 : false),
  });
  const ready = report.data?.status === "completed";
  const html = useQuery({
    queryKey: ["reports", reportId, "html"],
    queryFn: () => apiText(`/reports/${reportId}/html`),
    enabled: ready,
    staleTime: Infinity,
  });

  if (report.isLoading) return <LoadingState rows={6} />;
  if (report.error) {
    if (report.error instanceof ApiError && report.error.status === 404) return <EmptyState title="Report not found" />;
    return <ErrorState error={report.error} onRetry={() => void report.refetch()} />;
  }
  const r = report.data;
  if (!r) return null;
  return (
    <>
      <Button variant="ghost" size="sm" asChild className="mb-2 -ml-2">
        <Link href="/reports"><ArrowLeft aria-hidden /> All reports</Link>
      </Button>
      <PageHeader
        title={r.title}
        description={`Generated ${r.finished_at ? formatDateTime(r.finished_at, current?.timezone) : "…"}`}
        actions={
          ready ? (
            <>
              {r.pdf_status === "ready" ? (
                <Button onClick={() => void downloadFile(`/reports/${r.id}/pdf`, reportFilename(r, "pdf"))}>
                  <Download aria-hidden /> Download PDF
                </Button>
              ) : null}
              <Button variant="outline" onClick={() => void downloadFile(`/reports/${r.id}/html`, reportFilename(r, "html"))}>
                <Download aria-hidden /> Download HTML
              </Button>
            </>
          ) : null
        }
      />
      {!ready ? (
        <div className="space-y-2">
          <ReportStatusBadge report={r} />
          {r.error ? <Alert variant="destructive"><AlertDescription>{r.error}</AlertDescription></Alert> : null}
        </div>
      ) : (
        <div className="space-y-3">
          {r.pdf_status !== "ready" ? (
            <Alert>
              <AlertDescription>
                {r.pdf_error ?? "The PDF is not available."} You can also open the downloaded HTML file in a browser and print it
                to PDF.
              </AlertDescription>
            </Alert>
          ) : null}
          {html.isLoading ? (
            <LoadingState rows={8} label="Loading report" />
          ) : html.error ? (
            <ErrorState error={html.error} onRetry={() => void html.refetch()} />
          ) : (
            // sandbox with no permissions: the report cannot run scripts or reach the app.
            <iframe
              title={r.title}
              sandbox=""
              srcDoc={html.data}
              className="h-[80vh] w-full rounded-lg border bg-white"
            />
          )}
        </div>
      )}
    </>
  );
}
