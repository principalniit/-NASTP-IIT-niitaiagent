"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Bot, Loader2 } from "lucide-react";
import Link from "next/link";
import { useEffect } from "react";

import { ErrorState } from "@/components/app/states";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useCurrentOrg } from "@/lib/current-org";
import { keys, useAnalysis } from "@/lib/queries";
import type { AIAnalysis, AIKind } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

export const AI_KIND_LABELS: Record<AIKind, string> = {
  management_summary: "Management summary",
  issue_explanation: "Issue explanation",
  page_plan: "Page improvement plan",
  metadata_draft: "Title and description drafts",
  content_outline: "Content outline draft",
  question: "Question",
};

type Out = Record<string, unknown>;

const text = (value: unknown): string => (typeof value === "string" ? value : "");
const list = (value: unknown): unknown[] => (Array.isArray(value) ? value : []);
const strings = (value: unknown): string[] => list(value).filter((v): v is string => typeof v === "string");

/** Issue id to title, from whatever issues the evidence contains. */
function issueTitles(evidence: unknown, found: Map<string, string> = new Map()): Map<string, string> {
  if (Array.isArray(evidence)) evidence.forEach((item) => issueTitles(item, found));
  else if (evidence && typeof evidence === "object") {
    const record = evidence as Record<string, unknown>;
    if (typeof record.id === "string" && typeof record.rule_id === "string" && typeof record.title === "string") {
      found.set(record.id, record.title);
    }
    Object.values(record).forEach((value) => issueTitles(value, found));
  }
  return found;
}

function IssueLinks({ ids, titles }: { ids: unknown; titles: Map<string, string> }) {
  const values = strings(ids);
  if (!values.length) return null;
  return (
    <span className="mt-1 flex flex-wrap gap-1.5">
      {values.map((id) => (
        <Link
          key={id}
          href={`/issues/${id}`}
          className="rounded border px-1.5 py-0.5 text-xs text-primary underline-offset-4 hover:underline"
        >
          {titles.get(id) ?? "Related issue"}
        </Link>
      ))}
    </span>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <h3 className="text-sm font-semibold">{title}</h3>
      <div className="text-sm">{children}</div>
    </div>
  );
}

function DraftLinks({ ids }: { ids: string[] }) {
  if (!ids.length) return <p className="text-sm text-muted-foreground">No draft was needed: the page already matches.</p>;
  return (
    <p className="text-sm">
      {ids.length === 1 ? "A draft was" : `${ids.length} drafts were`} created for human review:{" "}
      {ids.map((id, i) => (
        <span key={id}>
          {i ? ", " : ""}
          <Link href={`/approvals/${id}`} className="font-medium text-primary underline-offset-4 hover:underline">
            open draft {ids.length > 1 ? i + 1 : ""}
          </Link>
        </span>
      ))}
      . Nothing is published automatically.
    </p>
  );
}

function Output({ analysis }: { analysis: AIAnalysis }) {
  const o = (analysis.output ?? {}) as Out;
  const titles = issueTitles(analysis.evidence);
  switch (analysis.kind) {
    case "management_summary":
      return (
        <div className="space-y-4">
          <p className="text-base font-medium">{text(o.headline)}</p>
          <p className="text-sm">{text(o.overview)}</p>
          <Section title="Key findings">
            <ul className="list-disc space-y-2 pl-5">
              {list(o.key_findings).map((f, i) => (
                <li key={i}>
                  {text((f as Out).statement)}
                  <IssueLinks ids={(f as Out).issue_ids} titles={titles} />
                </li>
              ))}
            </ul>
          </Section>
          <Section title="Recommended priorities">
            <ol className="list-decimal space-y-2 pl-5">
              {list(o.priorities).map((p, i) => (
                <li key={i}>
                  <span className="font-medium">{text((p as Out).action)}</span>
                  <span className="block text-muted-foreground">{text((p as Out).reason)}</span>
                  <IssueLinks ids={(p as Out).issue_ids} titles={titles} />
                </li>
              ))}
            </ol>
          </Section>
          {text(o.changes_since_previous) ? <Section title="Since the previous crawl">{text(o.changes_since_previous)}</Section> : null}
          {strings(o.data_limitations).length ? (
            <Section title="Limitations">
              <ul className="list-disc pl-5 text-muted-foreground">
                {strings(o.data_limitations).map((l) => <li key={l}>{l}</li>)}
              </ul>
            </Section>
          ) : null}
        </div>
      );
    case "issue_explanation":
      return (
        <div className="space-y-4">
          <p className="text-sm">{text(o.explanation)}</p>
          <Section title="Why it matters">{text(o.why_it_matters)}</Section>
          <Section title="Steps">
            <ol className="list-decimal space-y-1 pl-5">{strings(o.steps).map((s) => <li key={s}>{s}</li>)}</ol>
          </Section>
          <Section title="How to verify">{text(o.how_to_verify)}</Section>
          {strings(o.caveats).length ? (
            <Section title="Caveats">
              <ul className="list-disc pl-5 text-muted-foreground">{strings(o.caveats).map((c) => <li key={c}>{c}</li>)}</ul>
            </Section>
          ) : null}
        </div>
      );
    case "page_plan":
      return (
        <div className="space-y-4">
          <p className="text-sm">{text(o.summary)}</p>
          {list(o.improvements).length ? (
            <ul className="space-y-3">
              {list(o.improvements).map((item, i) => (
                <li key={i} className="text-sm">
                  <Badge variant="secondary" className="mr-2">{text((item as Out).area).replace(/_/g, " ")}</Badge>
                  {text((item as Out).suggestion)}
                  <IssueLinks ids={(item as Out).issue_ids} titles={titles} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">No improvements were suggested for this page.</p>
          )}
        </div>
      );
    case "metadata_draft":
      return (
        <div className="space-y-4">
          <Section title="Proposed title">
            <p className="rounded border bg-muted/40 px-3 py-2">{text(o.title)}</p>
          </Section>
          <Section title="Proposed meta description">
            <p className="rounded border bg-muted/40 px-3 py-2">{text(o.meta_description)}</p>
          </Section>
          <Section title="Rationale">{text(o.rationale)}</Section>
          {strings(o.facts_used).length ? (
            <Section title="Based on this page text">
              <ul className="list-disc pl-5 text-muted-foreground">{strings(o.facts_used).map((f) => <li key={f}>{f}</li>)}</ul>
            </Section>
          ) : null}
          <DraftLinks ids={analysis.draft_ids} />
        </div>
      );
    case "content_outline":
      return (
        <div className="space-y-4">
          <p className="text-sm">{text(o.purpose)}</p>
          {list(o.sections).map((section, i) => (
            <Section key={i} title={text((section as Out).heading)}>
              <ul className="list-disc pl-5">
                {strings((section as Out).points).map((p) => <li key={p}>{p}</li>)}
                {strings((section as Out).facts_needed).map((f) => (
                  <li key={f} className="text-muted-foreground">{f.startsWith("[verify") ? f : `[verify: ${f}]`}</li>
                ))}
              </ul>
            </Section>
          ))}
          <DraftLinks ids={analysis.draft_ids} />
        </div>
      );
    case "question":
      return (
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">Q: {analysis.params.question}</p>
          <p className="text-sm">{text(o.answer)}</p>
          <IssueLinks ids={o.issue_ids} titles={titles} />
          {strings(o.tools_used).length ? (
            <p className="text-xs text-muted-foreground">Looked up: {strings(o.tools_used).join(", ").replace(/_/g, " ")}</p>
          ) : null}
        </div>
      );
  }
}

export function AnalysisBody({ analysis }: { analysis: AIAnalysis }) {
  const { current } = useCurrentOrg();
  if (analysis.status === "queued" || analysis.status === "running") {
    return (
      <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" aria-hidden />
        {analysis.status === "queued" ? "Waiting for the worker…" : "The AI assistant is working on this…"} Local models
        can take a few minutes.
      </p>
    );
  }
  if (analysis.status === "failed") {
    return (
      <Alert variant="destructive">
        <AlertTitle>This AI task did not produce a usable result</AlertTitle>
        <AlertDescription>
          <p>{analysis.error ?? "Unknown error."}</p>
          {analysis.grounding.violations?.length ? (
            <ul className="mt-2 list-disc pl-5">
              {analysis.grounding.violations.map((v) => <li key={v}>{v}</li>)}
            </ul>
          ) : null}
        </AlertDescription>
      </Alert>
    );
  }
  return (
    <div className="space-y-4">
      <Output analysis={analysis} />
      {analysis.grounding.warnings?.length ? (
        <Alert>
          <AlertTitle>Check before using</AlertTitle>
          <AlertDescription>
            <ul className="list-disc pl-5">{analysis.grounding.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
          </AlertDescription>
        </Alert>
      ) : null}
      <p className="border-t pt-3 text-xs text-muted-foreground">
        Generated {analysis.finished_at ? formatDateTime(analysis.finished_at, current?.timezone) : ""} by {analysis.model}{" "}
        from this project&apos;s crawl data only, and checked for unsupported numbers and claims. AI output can still be
        wrong: verify before acting.
      </p>
    </div>
  );
}

/** Loads one analysis by id and renders it in a card, polling until it finishes. */
export function AnalysisCard({ id, title }: { id: string; title?: string }) {
  const query = useAnalysis(id);
  const queryClient = useQueryClient();
  const projectId = query.data?.project_id;
  const finished = query.data?.status === "completed";
  useEffect(() => {
    // A finished task may have created drafts or recommendations shown elsewhere on the page.
    if (!finished || !projectId) return;
    void queryClient.invalidateQueries({ queryKey: keys.drafts(projectId) });
    void queryClient.invalidateQueries({ queryKey: keys.recommendations(projectId) });
  }, [finished, projectId, queryClient]);
  if (query.error) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  const analysis = query.data;
  return (
    <Card data-testid="ai-result">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Bot className="size-4" aria-hidden /> {title ?? (analysis ? AI_KIND_LABELS[analysis.kind] : "AI result")}
          <Badge variant="outline">AI-generated</Badge>
        </CardTitle>
        {analysis?.kind === "issue_explanation" || analysis?.kind === "page_plan" ? (
          <CardDescription>Saved to AI Recommendations when complete.</CardDescription>
        ) : null}
      </CardHeader>
      <CardContent>
        {analysis ? <AnalysisBody analysis={analysis} /> : <p className="text-sm text-muted-foreground">Loading…</p>}
      </CardContent>
    </Card>
  );
}
