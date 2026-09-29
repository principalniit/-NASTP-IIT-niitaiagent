"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ShieldAlert } from "lucide-react";
import Link from "next/link";
import { useId, useState } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/app/states";
import { DraftSourceLabel, DraftStatusBadge } from "@/components/drafts/draft-status";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError } from "@/lib/api";
import { useCurrentOrg } from "@/lib/current-org";
import { keys, useDraft } from "@/lib/queries";
import { useSession } from "@/lib/session";
import { APPROVAL_ACTION_LABELS, DRAFT_FIELD_LABELS, type Draft, type DraftDetail } from "@/lib/types";
import { formatDateTime, pathOf } from "@/lib/utils";

// Common guidance for search snippets; the project's own thresholds apply in the audit.
const LENGTH_HINT: Partial<Record<Draft["field"], string>> = {
  title: "Titles of about 30 to 60 characters usually display in full.",
  meta_description: "Descriptions of about 70 to 160 characters usually display in full.",
};

type Action = "submit" | "approve" | "reject" | "reopen" | "mark-published" | "rollback";

function useDraftAction(draft: DraftDetail) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ action, body }: { action: Action; body: Record<string, string | null> }) =>
      api<Draft>(`/drafts/${draft.id}/${action}`, { method: "POST", body }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: keys.draft(draft.id) });
      void queryClient.invalidateQueries({ queryKey: keys.drafts(draft.project_id) });
    },
  });
}

function Content({ label, value, field }: { label: string; value: string | null; field: Draft["field"] }) {
  const measured = field === "title" || field === "meta_description";
  return (
    <div className="space-y-1.5">
      <h3 className="text-sm font-semibold">{label}</h3>
      {value ? (
        <p className="rounded border bg-muted/40 px-3 py-2 text-sm whitespace-pre-wrap break-words">{value}</p>
      ) : (
        <p className="rounded border border-dashed px-3 py-2 text-sm text-muted-foreground">Nothing recorded</p>
      )}
      {measured && value ? <p className="text-xs text-muted-foreground tabular-nums">{value.length} characters</p> : null}
    </div>
  );
}

function EditForm({ draft, onDone }: { draft: DraftDetail; onDone: () => void }) {
  const queryClient = useQueryClient();
  const contentId = useId();
  const reasonId = useId();
  const [content, setContent] = useState(draft.proposed_content);
  const [reason, setReason] = useState("");
  const save = useMutation({
    mutationFn: () => api<Draft>(`/drafts/${draft.id}`, { method: "PATCH", body: { proposed_content: content, reason } }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: keys.draft(draft.id) });
      onDone();
    },
  });
  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      <div className="space-y-1.5">
        <Label htmlFor={contentId}>Proposed content</Label>
        <Textarea id={contentId} rows={draft.field.startsWith("content") ? 12 : 3} value={content} onChange={(e) => setContent(e.target.value)} />
        {LENGTH_HINT[draft.field] ? (
          <p className="text-xs text-muted-foreground tabular-nums">{content.length} characters. {LENGTH_HINT[draft.field]}</p>
        ) : null}
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={reasonId}>What changed and why</Label>
        <Input id={reasonId} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={2000} />
      </div>
      {save.error ? (
        <Alert variant="destructive"><AlertDescription>{save.error instanceof ApiError ? save.error.message : "Could not save."}</AlertDescription></Alert>
      ) : null}
      <div className="flex gap-2">
        <Button type="submit" disabled={save.isPending || !content.trim() || reason.trim().length < 5}>Save as new version</Button>
        <Button type="button" variant="ghost" onClick={onDone}>Cancel</Button>
      </div>
    </form>
  );
}

function Decision({ draft }: { draft: DraftDetail }) {
  const { can } = useCurrentOrg();
  const { me } = useSession();
  const action = useDraftAction(draft);
  const commentId = useId();
  const sourceId = useId();
  const [comment, setComment] = useState("");
  const [source, setSource] = useState("");
  const [editing, setEditing] = useState(false);
  const run = (name: Action, body: Record<string, string | null> = {}) =>
    action.mutate({ action: name, body }, { onSuccess: () => { setComment(""); setSource(""); } });
  const note = comment.trim() || null;
  const userId = me?.user.id;
  const submitter = [...draft.trail].reverse().find((t) => t.action === "submitted" && t.version === draft.version)?.actor_id;
  const ownWork = !!userId && (userId === draft.version_author_id || userId === submitter);
  const author = can("drafts:create");
  const reviewer = can("approvals:decide");

  if (editing) return <EditForm draft={draft} onDone={() => setEditing(false)} />;

  const commentBox = (label: string, required = false) => (
    <div className="space-y-1.5">
      <Label htmlFor={commentId}>{label}{required ? "" : " (optional)"}</Label>
      <Textarea id={commentId} rows={2} maxLength={2000} value={comment} onChange={(e) => setComment(e.target.value)} />
    </div>
  );

  let body: React.ReactNode = null;
  switch (draft.status) {
    case "draft":
    case "rejected":
      body = author ? (
        <div className="space-y-3">
          {draft.status === "rejected" ? <p className="text-sm">Edit the draft to address the reviewer&apos;s comments, then submit it again.</p> : null}
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => setEditing(true)}>Edit</Button>
            {draft.status === "draft" ? <Button onClick={() => run("submit", { comment: note })} disabled={action.isPending}>Submit for review</Button> : null}
            {draft.status === "rejected" ? <Button variant="ghost" onClick={() => run("reopen", { comment: note })} disabled={action.isPending}>Reopen as draft</Button> : null}
          </div>
        </div>
      ) : null;
      break;
    case "pending_review":
      body = reviewer ? (
        ownWork ? (
          <p className="text-sm">You wrote or submitted this version, so another reviewer must decide on it.</p>
        ) : (
          <div className="space-y-3">
            {draft.protected ? (
              <div className="space-y-1.5">
                <Label htmlFor={sourceId}>Verified source (required)</Label>
                <Input id={sourceId} value={source} onChange={(e) => setSource(e.target.value)} maxLength={2048} placeholder="Approved notice, document or page confirming these facts" />
              </div>
            ) : null}
            {commentBox("Comment")}
            <p className="text-xs text-muted-foreground">A comment is required to reject.</p>
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => run("approve", { comment: note, source_reference: source.trim() || null })} disabled={action.isPending || (draft.protected && !source.trim())}>
                Approve
              </Button>
              <Button variant="outline" onClick={() => run("reject", { comment: comment.trim() })} disabled={action.isPending || comment.trim().length < 3}>
                Reject
              </Button>
            </div>
          </div>
        )
      ) : (
        <p className="text-sm text-muted-foreground">Waiting for an SEO manager or administrator to review.</p>
      );
      break;
    case "approved":
      body = (
        <div className="space-y-3">
          <p className="text-sm">
            Approved. When someone has made this change on the website, record it here. This platform does not change the
            website itself.
          </p>
          {reviewer ? commentBox("Where and when it was changed") : null}
          <div className="flex flex-wrap gap-2">
            {reviewer ? <Button onClick={() => run("mark-published", { comment: note })} disabled={action.isPending}>Mark as published</Button> : null}
            {author ? <Button variant="ghost" onClick={() => run("reopen", { comment: note })} disabled={action.isPending}>Reopen as draft</Button> : null}
          </div>
        </div>
      );
      break;
    case "published":
      body = reviewer ? (
        <div className="space-y-3">
          <p className="text-sm">If the change was undone on the website, record the rollback. The original content is kept above.</p>
          {commentBox("Why it was rolled back", true)}
          <Button variant="outline" onClick={() => run("rollback", { comment: comment.trim() })} disabled={action.isPending || comment.trim().length < 3}>
            Record rollback
          </Button>
        </div>
      ) : null;
      break;
    case "rolled_back":
      body = <p className="text-sm text-muted-foreground">This change was rolled back. Create a new draft to propose it again.</p>;
      break;
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>Review</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {body ?? <p className="text-sm text-muted-foreground">Your role cannot act on this draft at this stage.</p>}
        {action.error ? (
          <Alert variant="destructive"><AlertDescription>{action.error instanceof ApiError ? action.error.message : "The action failed."}</AlertDescription></Alert>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function DraftDetailView({ draftId }: { draftId: string }) {
  const query = useDraft(draftId);
  const { current } = useCurrentOrg();
  if (query.isLoading) return <LoadingState rows={6} />;
  if (query.error) {
    if (query.error instanceof ApiError && query.error.status === 404) return <EmptyState title="Draft not found" />;
    return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  }
  const draft = query.data;
  if (!draft) return null;
  const tz = current?.timezone;
  const who = (id: string | null) => (id ? (draft.people[id] ?? "A former member") : "AI assistant");
  const issueIds = draft.evidence.issue_ids ?? [];
  return (
    <>
      <Button variant="ghost" size="sm" asChild className="mb-2 -ml-2">
        <Link href="/approvals"><ArrowLeft aria-hidden /> All drafts</Link>
      </Button>
      <div className="mb-6 space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <DraftStatusBadge status={draft.status} />
          <DraftSourceLabel source={draft.source} />
          <span className="text-xs text-muted-foreground">Version {draft.version}</span>
        </div>
        <h1 className="text-2xl font-semibold tracking-tight">{DRAFT_FIELD_LABELS[draft.field]}</h1>
        <p className="text-sm break-all text-muted-foreground">{draft.page_url}</p>
      </div>
      {draft.protected ? (
        <Alert className="mb-6">
          <ShieldAlert aria-hidden />
          <AlertTitle>This draft touches official information</AlertTitle>
          <AlertDescription>
            <ul className="list-disc pl-5">{draft.protected_reasons.map((r) => <li key={r}>{r}</li>)}</ul>
            <p className="mt-1">Approval requires a verified source reference. Check every fact against an approved source.</p>
          </AlertDescription>
        </Alert>
      ) : null}
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>Proposed change</CardTitle>
              <CardDescription>{draft.reason}</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-2">
              <Content label="Current (original)" value={draft.original_content} field={draft.field} />
              <Content label={`Proposed (version ${draft.version})`} value={draft.proposed_content} field={draft.field} />
            </CardContent>
          </Card>
          {issueIds.length || draft.evidence.facts_used?.length || draft.evidence.warnings?.length ? (
            <Card>
              <CardHeader>
                <CardTitle>Evidence</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                {issueIds.length ? (
                  <div>
                    <h3 className="font-semibold">Issues this addresses</h3>
                    <ul className="mt-1 space-y-1">
                      {issueIds.map((id, i) => (
                        <li key={id}><Link href={`/issues/${id}`} className="text-primary underline-offset-4 hover:underline">Issue {i + 1}</Link></li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {draft.evidence.facts_used?.length ? (
                  <div>
                    <h3 className="font-semibold">Based on this page text</h3>
                    <ul className="mt-1 list-disc pl-5">{draft.evidence.facts_used.map((f) => <li key={f}>{f}</li>)}</ul>
                  </div>
                ) : null}
                {draft.evidence.warnings?.length ? (
                  <div>
                    <h3 className="font-semibold">Warnings</h3>
                    <ul className="mt-1 list-disc pl-5">{draft.evidence.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
                  </div>
                ) : null}
              </CardContent>
            </Card>
          ) : null}
          <Card>
            <CardHeader>
              <CardTitle>Version history</CardTitle>
            </CardHeader>
            <CardContent>
              <ol className="space-y-4">
                {[...draft.versions].reverse().map((v) => (
                  <li key={v.version} className="border-l-2 pl-3">
                    <p className="text-xs text-muted-foreground">
                      Version {v.version} · {v.source === "ai" ? "AI assistant" : who(v.edited_by_id)} · {formatDateTime(v.created_at, tz)}
                    </p>
                    <p className="mt-1 text-sm whitespace-pre-wrap break-words">{v.proposed_content}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{v.reason}</p>
                  </li>
                ))}
              </ol>
            </CardContent>
          </Card>
        </div>
        <div className="space-y-6">
          <Decision draft={draft} />
          <Card>
            <CardHeader>
              <CardTitle>Approval trail</CardTitle>
            </CardHeader>
            <CardContent>
              <ol className="space-y-3 text-sm" aria-label="Approval trail">
                {draft.trail.map((t) => (
                  <li key={t.id}>
                    <span className="font-medium">{APPROVAL_ACTION_LABELS[t.action]}</span>{" "}
                    <span className="text-muted-foreground">by {who(t.actor_id)} · v{t.version} · {formatDateTime(t.created_at, tz)}</span>
                    {t.comment ? <span className="block">“{t.comment}”</span> : null}
                    {t.source_reference ? <span className="block text-xs">Source: {t.source_reference}</span> : null}
                  </li>
                ))}
              </ol>
              {draft.source_reference ? <p className="mt-3 text-xs">Verified source: {draft.source_reference}</p> : null}
              <p className="mt-3 text-xs text-muted-foreground">Page: {pathOf(draft.page_url)}</p>
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}
