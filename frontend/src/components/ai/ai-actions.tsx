"use client";

import { Sparkles } from "lucide-react";
import Link from "next/link";
import { useId, useState } from "react";

import { AIStatusNotice, useAIReady, useRequestAnalysis } from "@/components/ai/ai-status";
import { AnalysisCard } from "@/components/ai/analysis-result";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api";
import { useCurrentOrg } from "@/lib/current-org";
import { useAnalyses, useDrafts } from "@/lib/queries";
import { DRAFT_FIELD_LABELS, type AIKind, type Issue } from "@/lib/types";

function failure(error: unknown): string {
  return error instanceof ApiError ? error.message : "Could not start the AI task.";
}

/** "Explain with AI" for one issue, showing the latest explanation if there is one. */
export function ExplainIssue({ issue }: { issue: Issue }) {
  const { can } = useCurrentOrg();
  const { ready, isLoading } = useAIReady();
  const latest = useAnalyses(issue.project_id, { kind: "issue_explanation", subject_id: issue.id, page_size: 1 });
  const request = useRequestAnalysis(issue.project_id);
  const id = latest.data?.items[0]?.id;
  const allowed = can("issues:triage");
  if (!id && !allowed) return null;
  return (
    <div className="space-y-3">
      {id ? <AnalysisCard id={id} title="AI explanation" /> : null}
      {allowed ? (
        <Card>
          <CardHeader>
            <CardTitle>AI assistant</CardTitle>
            <CardDescription>A plain-language explanation and fix steps, using only this issue&apos;s evidence.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {!isLoading && !ready ? <AIStatusNotice compact /> : null}
            <Button
              variant="outline"
              onClick={() => request.mutate({ kind: "issue_explanation", issue_id: issue.id })}
              disabled={!ready || request.isPending || issue.resolution_status === "resolved"}
            >
              <Sparkles aria-hidden /> {id ? "Explain again" : "Explain with AI"}
            </Button>
            {request.error ? <Alert variant="destructive"><AlertDescription>{failure(request.error)}</AlertDescription></Alert> : null}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

const PAGE_TASKS: { kind: AIKind; label: string; permission: string }[] = [
  { kind: "metadata_draft", label: "Draft title and description", permission: "drafts:create" },
  { kind: "content_outline", label: "Draft content outline", permission: "drafts:create" },
  { kind: "page_plan", label: "Suggest improvements", permission: "issues:triage" },
];

/** AI drafting for one crawled page, plus the drafts that already exist for it. */
export function PageAssistant({ projectId, pageUrl, latestCrawl }: { projectId: string; pageUrl: string; latestCrawl: boolean }) {
  const { can } = useCurrentOrg();
  const { ready, isLoading } = useAIReady();
  const goalId = useId();
  const [goal, setGoal] = useState("");
  const request = useRequestAnalysis(projectId);
  const latest = useAnalyses(projectId, { page_url: pageUrl, page_size: 1 });
  const drafts = useDrafts(projectId, { page_url: pageUrl });
  const tasks = PAGE_TASKS.filter((t) => can(t.permission));
  const id = latest.data?.items[0]?.id;
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>AI assistant</CardTitle>
          <CardDescription>
            Drafts use only this page&apos;s own text and issues. They go to Approvals for human review; nothing is published.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {!latestCrawl ? (
            <p className="text-sm text-muted-foreground">
              AI drafts use the latest analysed crawl. Open this page from the latest crawl to draft changes.
            </p>
          ) : tasks.length === 0 ? (
            <p className="text-sm text-muted-foreground">Your role can view drafts but not request them.</p>
          ) : (
            <>
              {!isLoading && !ready ? <AIStatusNotice compact /> : null}
              <div className="space-y-1.5">
                <Label htmlFor={goalId}>Goal for the outline (optional)</Label>
                <Input id={goalId} value={goal} maxLength={300} onChange={(e) => setGoal(e.target.value)} placeholder="For example: make the steps to apply clearer" />
              </div>
              <div className="flex flex-wrap gap-2">
                {tasks.map((t) => (
                  <Button
                    key={t.kind}
                    variant="outline"
                    size="sm"
                    disabled={!ready || request.isPending}
                    onClick={() =>
                      request.mutate({ kind: t.kind, page_url: pageUrl, goal: t.kind === "content_outline" && goal.trim() ? goal.trim() : undefined })
                    }
                  >
                    <Sparkles aria-hidden /> {t.label}
                  </Button>
                ))}
              </div>
              {request.error ? <Alert variant="destructive"><AlertDescription>{failure(request.error)}</AlertDescription></Alert> : null}
            </>
          )}
          {drafts.data?.items.length ? (
            <div className="border-t pt-3">
              <h3 className="text-sm font-semibold">Drafts for this page</h3>
              <ul className="mt-1 space-y-1 text-sm">
                {drafts.data.items.map((d) => (
                  <li key={d.id}>
                    <Link href={`/approvals/${d.id}`} className="text-primary underline-offset-4 hover:underline">
                      {DRAFT_FIELD_LABELS[d.field]}
                    </Link>{" "}
                    <span className="text-muted-foreground">· {d.status.replace(/_/g, " ")} · v{d.version}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </CardContent>
      </Card>
      {id ? <AnalysisCard id={id} /> : null}
    </div>
  );
}
