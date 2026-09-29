"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import Link from "next/link";
import { useId, useState } from "react";

import { AIStatusNotice, useAIReady, useRequestAnalysis } from "@/components/ai/ai-status";
import { AI_KIND_LABELS, AnalysisCard } from "@/components/ai/analysis-result";
import { PageHeader } from "@/components/app/page-header";
import { EmptyState, ErrorState, LoadingState } from "@/components/app/states";
import { AnalysisGate } from "@/components/seo/analysis-gate";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { NativeSelect } from "@/components/ui/native-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError } from "@/lib/api";
import { useCurrentOrg } from "@/lib/current-org";
import { keys, useAnalyses, useRecommendations } from "@/lib/queries";
import type { Project, Recommendation, RecommendationStatus } from "@/lib/types";
import { formatDateTime, pathOf } from "@/lib/utils";

function errorText(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

function SummaryPanel({ project }: { project: Project }) {
  const { can } = useCurrentOrg();
  const { ready } = useAIReady();
  const latest = useAnalyses(project.id, { kind: "management_summary", page_size: 1 });
  const request = useRequestAnalysis(project.id);
  const id = latest.data?.items[0]?.id;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">Management summary</h2>
        {can("reports:generate") ? (
          <Button size="sm" onClick={() => request.mutate({ kind: "management_summary" })} disabled={!ready || request.isPending}>
            <Sparkles aria-hidden /> {id ? "Generate a new summary" : "Generate summary"}
          </Button>
        ) : null}
      </div>
      {request.error ? (
        <Alert variant="destructive"><AlertDescription>{errorText(request.error, "Could not start the summary.")}</AlertDescription></Alert>
      ) : null}
      {latest.isLoading ? (
        <LoadingState rows={3} />
      ) : id ? (
        <AnalysisCard id={id} title="Latest summary" />
      ) : (
        <EmptyState
          title="No summary yet"
          description="A plain-language summary of the latest analysed crawl for leadership, grounded in the issues found."
        />
      )}
    </div>
  );
}

function AskPanel({ project }: { project: Project }) {
  const { can } = useCurrentOrg();
  const { ready } = useAIReady();
  const fieldId = useId();
  const [question, setQuestion] = useState("");
  const latest = useAnalyses(project.id, { kind: "question", page_size: 1 });
  const request = useRequestAnalysis(project.id);
  const id = latest.data?.items[0]?.id;
  if (!can("issues:triage")) return null;
  return (
    <div className="space-y-3">
      <h2 className="text-lg font-semibold">Ask about this site</h2>
      <form
        className="space-y-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (question.trim().length >= 3) request.mutate({ kind: "question", question: question.trim() }, { onSuccess: () => setQuestion("") });
        }}
      >
        <label htmlFor={fieldId} className="text-sm text-muted-foreground">
          Answers use only this project&apos;s crawl data. The assistant says so when the data does not contain an answer.
        </label>
        <Textarea
          id={fieldId}
          rows={2}
          maxLength={500}
          placeholder="Which pages should we fix first?"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <Button type="submit" size="sm" disabled={!ready || request.isPending || question.trim().length < 3}>
          Ask
        </Button>
      </form>
      {request.error ? (
        <Alert variant="destructive"><AlertDescription>{errorText(request.error, "Could not send the question.")}</AlertDescription></Alert>
      ) : null}
      {id ? <AnalysisCard id={id} title="Latest answer" /> : null}
    </div>
  );
}

function RecommendationCard({ rec }: { rec: Recommendation }) {
  const { can, current } = useCurrentOrg();
  const queryClient = useQueryClient();
  const update = useMutation({
    mutationFn: (status: RecommendationStatus) =>
      api<Recommendation>(`/recommendations/${rec.id}`, { method: "PATCH", body: { status } }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: keys.recommendations(rec.project_id) }),
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{rec.title}</CardTitle>
        <CardDescription>
          {rec.page_url ? <span className="break-all">{pathOf(rec.page_url)} · </span> : null}
          AI-generated {formatDateTime(rec.created_at, current?.timezone)}
          {rec.status !== "open" ? <Badge variant="secondary" className="ml-2">{rec.status}</Badge> : null}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p>{rec.body}</p>
        {rec.steps.length ? <ol className="list-decimal space-y-1 pl-5">{rec.steps.map((s) => <li key={s}>{s}</li>)}</ol> : null}
        <div className="flex flex-wrap items-center gap-2">
          {rec.issue_ids.map((id, i) => (
            <Link key={id} href={`/issues/${id}`} className="text-xs text-primary underline-offset-4 hover:underline">
              Related issue {rec.issue_ids.length > 1 ? i + 1 : ""}
            </Link>
          ))}
          {can("issues:triage") ? (
            <span className="ml-auto flex gap-2">
              {rec.status !== "accepted" ? (
                <Button size="sm" variant="outline" onClick={() => update.mutate("accepted")} disabled={update.isPending}>Accept</Button>
              ) : null}
              {rec.status !== "dismissed" ? (
                <Button size="sm" variant="ghost" onClick={() => update.mutate("dismissed")} disabled={update.isPending}>Dismiss</Button>
              ) : null}
              {rec.status !== "open" ? (
                <Button size="sm" variant="ghost" onClick={() => update.mutate("open")} disabled={update.isPending}>Reopen</Button>
              ) : null}
            </span>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

function RecommendationList({ project }: { project: Project }) {
  const [status, setStatus] = useState<RecommendationStatus | "">("open");
  const recs = useRecommendations(project.id, status);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">Recommendations</h2>
        <div className="flex items-center gap-2">
          <label htmlFor="rec-status" className="text-sm">Show</label>
          <NativeSelect id="rec-status" className="w-40" value={status} onChange={(e) => setStatus(e.target.value as RecommendationStatus | "")}>
            <option value="open">Open</option>
            <option value="accepted">Accepted</option>
            <option value="dismissed">Dismissed</option>
            <option value="">All</option>
          </NativeSelect>
        </div>
      </div>
      {recs.isLoading ? (
        <LoadingState rows={3} />
      ) : recs.error ? (
        <ErrorState error={recs.error} onRetry={() => void recs.refetch()} />
      ) : recs.data?.items.length ? (
        <div className="space-y-3">{recs.data.items.map((r) => <RecommendationCard key={r.id} rec={r} />)}</div>
      ) : (
        <EmptyState
          title="No recommendations"
          description="Use “Explain with AI” on an issue, or “Suggest improvements” on a crawled page, to get step-by-step recommendations."
        />
      )}
    </div>
  );
}

function RecentTasks({ project }: { project: Project }) {
  const { current } = useCurrentOrg();
  const tasks = useAnalyses(project.id, { page_size: 10 });
  if (!tasks.data?.items.length) return null;
  return (
    <div className="space-y-3">
      <h2 className="text-lg font-semibold">Recent AI tasks</h2>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Task</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Requested</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {tasks.data.items.map((t) => (
            <TableRow key={t.id}>
              <TableCell>
                {AI_KIND_LABELS[t.kind]}
                {t.params.page_url ? <span className="block text-xs text-muted-foreground">{pathOf(t.params.page_url)}</span> : null}
              </TableCell>
              <TableCell>
                <Badge variant={t.status === "completed" ? "success" : t.status === "failed" ? "destructive" : "secondary"}>{t.status}</Badge>
                {t.error ? <span className="block max-w-md text-xs text-muted-foreground">{t.error}</span> : null}
              </TableCell>
              <TableCell className="whitespace-nowrap">{formatDateTime(t.created_at, current?.timezone)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

export function RecommendationsView() {
  return (
    <AnalysisGate
      header={(picker) => (
        <PageHeader
          title="AI Recommendations"
          description="Explanations and next steps generated only from this project's crawl evidence. Suggestions, never automatic changes."
          actions={picker}
        />
      )}
    >
      {({ project }) => (
        <>
          <AIStatusNotice />
          <div className="grid gap-8 lg:grid-cols-2">
            <SummaryPanel project={project} />
            <div className="space-y-8">
              <AskPanel project={project} />
              <RecommendationList project={project} />
            </div>
          </div>
          <div className="mt-8">
            <RecentTasks project={project} />
          </div>
        </>
      )}
    </AnalysisGate>
  );
}
