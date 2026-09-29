"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink } from "lucide-react";
import Link from "next/link";
import { useId, useState } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/app/states";
import { SeverityBadge } from "@/components/seo/severity";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError } from "@/lib/api";
import { useCurrentOrg } from "@/lib/current-org";
import { keys, useIssue } from "@/lib/queries";
import { CATEGORY_LABELS, type Issue } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

function humanise(key: string): string {
  const text = key.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function EvidenceValue({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <span className="text-muted-foreground">none</span>;
  if (typeof value === "boolean") return <span>{value ? "yes" : "no"}</span>;
  if (typeof value === "string" || typeof value === "number") {
    const text = String(value);
    return /^https?:\/\//.test(text) ? <span className="break-all">{text}</span> : <span className="break-words">{text}</span>;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-muted-foreground">none</span>;
    return (
      <ul className="list-disc space-y-0.5 pl-4">
        {value.map((item, i) => (
          <li key={i}>
            <EvidenceValue value={item} />
          </li>
        ))}
      </ul>
    );
  }
  if (typeof value === "object") {
    return (
      <span className="block space-y-0.5">
        {Object.entries(value as Record<string, unknown>).map(([k, v]) => (
          <span key={k} className="block">
            <span className="text-muted-foreground">{humanise(k)}: </span>
            <EvidenceValue value={v} />
          </span>
        ))}
      </span>
    );
  }
  return <span>{String(value)}</span>;
}

export function IssueDetailView({ issueId }: { issueId: string }) {
  const issue = useIssue(issueId);
  const { current, can } = useCurrentOrg();
  if (issue.isLoading) return <LoadingState rows={6} />;
  if (issue.error) {
    if (issue.error instanceof ApiError && issue.error.status === 404) return <EmptyState title="Issue not found" />;
    return <ErrorState error={issue.error} onRetry={() => void issue.refetch()} />;
  }
  const i = issue.data;
  if (!i) return null;
  const tz = current?.timezone;
  return (
    <>
      <Button variant="ghost" size="sm" asChild className="mb-2 -ml-2">
        <Link href="/issues">
          <ArrowLeft aria-hidden /> All issues
        </Link>
      </Button>
      <div className="mb-6 space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <SeverityBadge severity={i.severity} />
          <Badge variant="secondary">{CATEGORY_LABELS[i.category]}</Badge>
          <Badge variant={i.resolution_status === "open" ? "outline" : i.resolution_status === "resolved" ? "success" : "secondary"}>
            {i.resolution_status}
          </Badge>
          <span className="font-mono text-xs text-muted-foreground">{i.rule_id}</span>
        </div>
        <h1 className="text-2xl font-semibold tracking-tight">{i.title}</h1>
        <p className="text-sm text-muted-foreground">
          {i.scope === "site" ? "Affects the whole site" : `Affects ${i.affected_page_count} page${i.affected_page_count === 1 ? "" : "s"}`}
          {i.affected_url ? <> · <span className="break-all">{i.affected_url}</span></> : null}
        </p>
      </div>
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>Why it matters</CardTitle>
            </CardHeader>
            <CardContent className="text-sm">{i.description}</CardContent>
          </Card>
          <Card className="border-primary/40">
            <CardHeader>
              <CardTitle>Recommendation</CardTitle>
            </CardHeader>
            <CardContent className="text-sm">{i.recommendation}</CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Evidence</CardTitle>
              <CardDescription>Observed in the crawl of {formatDateTime(i.last_detected_at, tz)}.</CardDescription>
            </CardHeader>
            <CardContent>
              <dl className="divide-y text-sm">
                {Object.entries(i.evidence).map(([key, value]) => (
                  <div key={key} className="grid gap-1 py-2 sm:grid-cols-3">
                    <dt className="text-muted-foreground">{humanise(key)}</dt>
                    <dd className="sm:col-span-2"><EvidenceValue value={value} /></dd>
                  </div>
                ))}
              </dl>
            </CardContent>
          </Card>
          {i.scope !== "page" && i.affected_urls.length > 1 ? (
            <Card>
              <CardHeader>
                <CardTitle>Affected URLs</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-1 text-sm">
                  {i.affected_urls.map((url) => (
                    <li key={url}>
                      <a href={url} target="_blank" rel="noopener noreferrer nofollow" className="inline-flex items-center gap-1 break-all text-primary underline-offset-4 hover:underline">
                        {url} <ExternalLink className="size-3 shrink-0" aria-hidden />
                        <span className="sr-only">(opens in a new tab)</span>
                      </a>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ) : null}
        </div>
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Priority {i.priority_score.toFixed(0)}</CardTitle>
              <CardDescription>Out of 100. Why this issue ranks where it does:</CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Factor</TableHead>
                    <TableHead className="text-right">Effect</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {i.priority_breakdown.map((f) => (
                    <TableRow key={f.factor}>
                      <TableCell>
                        <span className="font-medium">{humanise(f.factor)}</span>
                        <span className="block text-xs text-muted-foreground">{f.reason}</span>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {f.multiplier !== undefined ? `×${f.multiplier}` : `+${f.points}`}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>History</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="space-y-2 text-sm">
                <div><dt className="text-muted-foreground">First detected</dt><dd>{formatDateTime(i.first_detected_at, tz)}</dd></div>
                <div><dt className="text-muted-foreground">Last detected</dt><dd>{formatDateTime(i.last_detected_at, tz)}</dd></div>
                {i.resolved_at ? <div><dt className="text-muted-foreground">Resolved (verified by crawl)</dt><dd>{formatDateTime(i.resolved_at, tz)}</dd></div> : null}
                {i.recurrence_count ? <div><dt className="text-muted-foreground">Recurred</dt><dd>{i.recurrence_count} time{i.recurrence_count === 1 ? "" : "s"} after being resolved</dd></div> : null}
                <div><dt className="text-muted-foreground">Confidence · effort</dt><dd>{i.confidence} · {i.effort}</dd></div>
                <div>
                  <dt className="text-muted-foreground">Proposed change</dt>
                  <dd>No change has been proposed. Drafts and approvals arrive in Phase 4.</dd>
                </div>
              </dl>
            </CardContent>
          </Card>
          {can("issues:triage") ? <TriageCard issue={i} /> : null}
        </div>
      </div>
    </>
  );
}

function TriageCard({ issue }: { issue: Issue }) {
  const queryClient = useQueryClient();
  const noteId = useId();
  const [note, setNote] = useState(issue.triage_note ?? "");
  const triage = useMutation({
    mutationFn: (status: "open" | "ignored") =>
      api<Issue>(`/issues/${issue.id}`, { method: "PATCH", body: { resolution_status: status, note: note.trim() || null } }),
    onSuccess: (updated) => {
      queryClient.setQueryData(keys.issue(issue.id), updated);
      void queryClient.invalidateQueries({ queryKey: keys.issues(issue.project_id) });
    },
  });
  if (issue.resolution_status === "resolved") {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Triage</CardTitle>
          <CardDescription>This issue was resolved by a crawl. It reopens automatically if detected again.</CardDescription>
        </CardHeader>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>Triage</CardTitle>
        <CardDescription>
          Ignoring hides the issue from the open list. It still counts toward the score, because the score reflects
          the site as crawled.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-1.5">
          <label htmlFor={noteId} className="text-sm font-medium">Note (optional)</label>
          <Textarea id={noteId} rows={2} maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} />
        </div>
        {triage.error ? (
          <Alert variant="destructive">
            <AlertDescription>{triage.error instanceof ApiError ? triage.error.message : "Could not update the issue."}</AlertDescription>
          </Alert>
        ) : null}
        {issue.resolution_status === "open" ? (
          <Button variant="outline" onClick={() => triage.mutate("ignored")} disabled={triage.isPending}>
            Ignore issue
          </Button>
        ) : (
          <Button onClick={() => triage.mutate("open")} disabled={triage.isPending}>
            Reopen issue
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
