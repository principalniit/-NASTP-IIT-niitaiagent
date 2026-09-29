"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, ShieldAlert } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { describedBy, Field } from "@/components/app/field";
import { PageHeader } from "@/components/app/page-header";
import { EmptyState, ErrorState, LoadingState } from "@/components/app/states";
import { DraftSourceLabel, DraftStatusBadge } from "@/components/drafts/draft-status";
import { ProjectPicker, useProjectChoice } from "@/components/seo/project-picker";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { useCurrentOrg } from "@/lib/current-org";
import { applyApiErrors } from "@/lib/form-errors";
import { keys, useDrafts } from "@/lib/queries";
import { DRAFT_FIELD_LABELS, DRAFT_STATUS_LABELS, type Draft, type DraftField, type DraftStatus, type Project } from "@/lib/types";
import { formatDateTime, pathOf } from "@/lib/utils";

const schema = z.object({
  page_url: z.string().trim().min(1, "Enter the page address").max(2048),
  field: z.enum(["title", "meta_description", "h1", "content_outline", "content_section"]),
  original_content: z.string().max(20000).optional(),
  proposed_content: z.string().trim().min(1, "Enter the proposed content").max(20000),
  reason: z.string().trim().min(5, "Explain the change in at least 5 characters").max(2000),
});
type FormValues = z.infer<typeof schema>;

function NewDraftForm({ project, onDone }: { project: Project; onDone: () => void }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { page_url: project.root_url, field: "title", original_content: "", proposed_content: "", reason: "" },
  });
  const create = useMutation({
    mutationFn: (values: FormValues) =>
      api<Draft>(`/projects/${project.id}/drafts`, {
        method: "POST",
        body: { ...values, original_content: values.original_content || null },
      }),
    onSuccess: async (draft) => {
      await queryClient.invalidateQueries({ queryKey: keys.drafts(project.id) });
      onDone();
      router.push(`/approvals/${draft.id}`);
    },
    onError: (error) =>
      setFormError(
        applyApiErrors(error, form.setError, {
          page_url: "page_url",
          field: "field",
          original_content: "original_content",
          proposed_content: "proposed_content",
          reason: "reason",
        }),
      ),
  });
  const errors = form.formState.errors;
  return (
    <Card className="mb-6">
      <CardHeader>
        <CardTitle>New draft</CardTitle>
        <CardDescription>
          Propose a change for review. It is saved as a draft; nothing on the website changes.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form className="grid gap-4 md:grid-cols-2" onSubmit={form.handleSubmit((v) => { setFormError(null); create.mutate(v); })} noValidate>
          <Field id="d-url" label="Page address" hint="A full address or a path such as /admissions, on this project's website." error={errors.page_url?.message}>
            <Input id="d-url" aria-invalid={!!errors.page_url} aria-describedby={describedBy("d-url", errors.page_url?.message, "hint")} {...form.register("page_url")} />
          </Field>
          <Field id="d-field" label="What to change" error={errors.field?.message}>
            <NativeSelect id="d-field" {...form.register("field")}>
              {(Object.keys(DRAFT_FIELD_LABELS) as DraftField[]).map((f) => (
                <option key={f} value={f}>{DRAFT_FIELD_LABELS[f]}</option>
              ))}
            </NativeSelect>
          </Field>
          <Field id="d-original" label="Current content (optional)" hint="Kept unchanged for reference and rollback." error={errors.original_content?.message}>
            <Textarea id="d-original" rows={3} aria-describedby={describedBy("d-original", errors.original_content?.message, "hint")} {...form.register("original_content")} />
          </Field>
          <Field id="d-proposed" label="Proposed content" error={errors.proposed_content?.message}>
            <Textarea id="d-proposed" rows={3} aria-invalid={!!errors.proposed_content} aria-describedby={describedBy("d-proposed", errors.proposed_content?.message)} {...form.register("proposed_content")} />
          </Field>
          <div className="md:col-span-2">
            <Field id="d-reason" label="Reason for the change" error={errors.reason?.message}>
              <Textarea id="d-reason" rows={2} aria-invalid={!!errors.reason} aria-describedby={describedBy("d-reason", errors.reason?.message)} {...form.register("reason")} />
            </Field>
          </div>
          {formError ? (
            <Alert variant="destructive" className="md:col-span-2"><AlertDescription>{formError}</AlertDescription></Alert>
          ) : null}
          <div className="flex gap-2 md:col-span-2">
            <Button type="submit" disabled={create.isPending}>Save draft</Button>
            <Button type="button" variant="ghost" onClick={onDone}>Cancel</Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

export function DraftTable({ drafts }: { drafts: Draft[] }) {
  const { current } = useCurrentOrg();
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Change</TableHead>
          <TableHead>Page</TableHead>
          <TableHead>Status</TableHead>
          <TableHead className="text-right">Updated</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {drafts.map((d) => (
          <TableRow key={d.id}>
            <TableCell>
              <Link href={`/approvals/${d.id}`} className="font-medium text-primary underline-offset-4 hover:underline">
                {DRAFT_FIELD_LABELS[d.field]}
              </Link>
              <span className="mt-0.5 flex flex-wrap items-center gap-2">
                <DraftSourceLabel source={d.source} />
                <span className="text-xs text-muted-foreground">v{d.version}</span>
                {d.protected ? (
                  <span className="inline-flex items-center gap-1 text-xs">
                    <ShieldAlert className="size-3.5 text-warning" aria-hidden /> Official facts
                  </span>
                ) : null}
              </span>
            </TableCell>
            <TableCell className="max-w-xs break-all">{pathOf(d.page_url)}</TableCell>
            <TableCell><DraftStatusBadge status={d.status} /></TableCell>
            <TableCell className="text-right whitespace-nowrap">{formatDateTime(d.updated_at, current?.timezone)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export function ApprovalsView() {
  const { current, can } = useCurrentOrg();
  const choice = useProjectChoice(current?.id ?? null);
  const [status, setStatus] = useState<DraftStatus | "">("pending_review");
  const [creating, setCreating] = useState(false);
  const [page, setPage] = useState(1);
  const drafts = useDrafts(choice.project?.id ?? null, { status_filter: status, page });
  const header = (
    <PageHeader
      title="Approvals"
      description="Proposed content changes. Every change needs human approval by someone other than its author, and nothing is published automatically."
      actions={
        <>
          <ProjectPicker projects={choice.projects} project={choice.project} onChange={choice.choose} />
          {can("drafts:create") && choice.project && !creating ? (
            <Button onClick={() => setCreating(true)}><Plus aria-hidden /> New draft</Button>
          ) : null}
        </>
      }
    />
  );
  if (!current || choice.isLoading) return <LoadingState rows={4} />;
  if (!choice.project) {
    return (
      <>
        {header}
        <EmptyState title="No projects yet" description="Add a project to start proposing changes." />
      </>
    );
  }
  const data = drafts.data;
  return (
    <>
      {header}
      {creating ? <NewDraftForm project={choice.project} onDone={() => setCreating(false)} /> : null}
      <div className="mb-4 flex items-center gap-2">
        <label htmlFor="draft-status" className="text-sm font-medium">Status</label>
        <NativeSelect id="draft-status" className="w-48" value={status} onChange={(e) => { setStatus(e.target.value as DraftStatus | ""); setPage(1); }}>
          {(Object.keys(DRAFT_STATUS_LABELS) as DraftStatus[]).map((s) => (
            <option key={s} value={s}>{DRAFT_STATUS_LABELS[s]}</option>
          ))}
          <option value="">All</option>
        </NativeSelect>
      </div>
      {drafts.isLoading ? (
        <LoadingState rows={4} />
      ) : drafts.error ? (
        <ErrorState error={drafts.error} onRetry={() => void drafts.refetch()} />
      ) : data && data.items.length ? (
        <>
          <DraftTable drafts={data.items} />
          {data.total > data.page_size ? (
            <div className="mt-4 flex items-center justify-end gap-2 text-sm">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
              <span>Page {page} of {Math.ceil(data.total / data.page_size)}</span>
              <Button variant="outline" size="sm" disabled={page * data.page_size >= data.total} onClick={() => setPage(page + 1)}>Next</Button>
            </div>
          ) : null}
        </>
      ) : (
        <EmptyState
          title={status ? `No drafts are ${DRAFT_STATUS_LABELS[status].toLowerCase()}` : "No drafts yet"}
          description="Drafts come from the AI assistant on crawled pages, or from people using “New draft”."
        />
      )}
    </>
  );
}
