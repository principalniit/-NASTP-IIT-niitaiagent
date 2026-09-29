"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { describedBy, Field } from "@/components/app/field";
import { PageHeader } from "@/components/app/page-header";
import { CrawlStatusBadge } from "@/components/crawls/crawl-status";
import { StartCrawlButton } from "@/components/crawls/start-crawl";
import { EmptyState, ErrorState, LoadingState } from "@/components/app/states";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError } from "@/lib/api";
import { useCurrentOrg } from "@/lib/current-org";
import { applyApiErrors } from "@/lib/form-errors";
import {
  formatContentTypes,
  formatPageGroups,
  formatSources,
  parseContentTypes,
  parsePageGroups,
  parseSources,
  splitLines,
} from "@/lib/line-formats";
import { isActiveCrawl, keys, useCrawls, useProject, useProjectSettings } from "@/lib/queries";
import type { Project, ProjectSettings, ProjectSettingsData } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

export function ProjectDetailView({ projectId }: { projectId: string }) {
  const project = useProject(projectId);
  const settings = useProjectSettings(projectId);
  const { current, can } = useCurrentOrg();

  if (project.isLoading) return <LoadingState rows={5} />;
  if (project.error) {
    if (project.error instanceof ApiError && project.error.status === 404) {
      return <EmptyState title="Project not found" description="It may have been deleted, or you may not have access to it." />;
    }
    return <ErrorState error={project.error} onRetry={() => void project.refetch()} />;
  }
  if (!project.data) return null;

  const p = project.data;
  return (
    <>
      <PageHeader
        title={p.name}
        description={p.domain}
        actions={
          <Button variant="outline" size="sm" asChild>
            <a href={p.root_url} target="_blank" rel="noopener noreferrer">
              Visit site <ExternalLink aria-hidden />
              <span className="sr-only">(opens in a new tab)</span>
            </a>
          </Button>
        }
      />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          {settings.isLoading ? (
            <LoadingState rows={6} />
          ) : settings.error || !settings.data ? (
            <ErrorState error={settings.error} onRetry={() => void settings.refetch()} />
          ) : (
            <SettingsForm project={p} settings={settings.data} canEdit={can("project_settings:update")} />
          )}
        </div>
        <div className="space-y-6">
          <DetailsCard project={p} canEdit={can("projects:update")} timeZone={current?.timezone} />
          <CrawlHistoryCard project={p} canStart={can("crawls:start")} timeZone={current?.timezone} />
          {can("projects:delete") ? <DeleteCard project={p} /> : null}
        </div>
      </div>
    </>
  );
}

function CrawlHistoryCard({ project, canStart, timeZone }: { project: Project; canStart: boolean; timeZone?: string }) {
  const crawls = useCrawls(project.organisation_id, { project_id: project.id, page_size: 5 });
  const busy = crawls.data?.items.some((job) => isActiveCrawl(job)) ?? false;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Crawls</CardTitle>
        <CardDescription>The most recent crawls of this project.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {crawls.isLoading ? (
          <LoadingState rows={2} />
        ) : !crawls.data?.items.length ? (
          <p className="text-sm text-muted-foreground">No crawls have been run yet.</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {crawls.data.items.map((job) => (
              <li key={job.id} className="flex items-center justify-between gap-2">
                <Link href={`/crawls/${job.id}`} className="text-primary underline-offset-4 hover:underline">
                  {formatDateTime(job.created_at, timeZone)}
                </Link>
                <span className="flex items-center gap-2">
                  <span className="tabular-nums text-muted-foreground">{job.pages_discovered} pages</span>
                  <CrawlStatusBadge status={job.status} />
                </span>
              </li>
            ))}
          </ul>
        )}
        {canStart ? (
          busy ? (
            <p className="text-sm text-muted-foreground">A crawl is in progress.</p>
          ) : (
            <StartCrawlButton projectId={project.id} organisationId={project.organisation_id} />
          )
        ) : null}
      </CardContent>
    </Card>
  );
}

const detailsSchema = z.object({
  name: z.string().trim().min(1, "Enter a project name").max(200),
  description: z.string().max(2000),
});

function DetailsCard({ project, canEdit, timeZone }: { project: Project; canEdit: boolean; timeZone?: string }) {
  const queryClient = useQueryClient();
  const [saved, setSaved] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<z.infer<typeof detailsSchema>>({
    resolver: zodResolver(detailsSchema),
    defaultValues: { name: project.name, description: project.description ?? "" },
  });
  const save = useMutation({
    mutationFn: (values: z.infer<typeof detailsSchema>) =>
      api<Project>(`/projects/${project.id}`, {
        method: "PATCH",
        body: { name: values.name, description: values.description || null },
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData(keys.project(project.id), updated);
      void queryClient.invalidateQueries({ queryKey: keys.projects(project.organisation_id) });
      setSaved(true);
    },
    onError: (error) => setFormError(applyApiErrors(error, form.setError, { name: "name", description: "description" })),
  });
  const { errors } = form.formState;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Details</CardTitle>
        <CardDescription>
          Created {formatDateTime(project.created_at, timeZone)} · Root URL {project.root_url}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form
          noValidate
          className="space-y-4"
          onSubmit={form.handleSubmit((values) => {
            setSaved(false);
            setFormError(null);
            save.mutate(values);
          })}
        >
          {formError ? (
            <Alert variant="destructive">
              <AlertDescription>{formError}</AlertDescription>
            </Alert>
          ) : null}
          <fieldset disabled={!canEdit} className="space-y-4">
            <Field id="project-name" label="Name" error={errors.name?.message}>
              <Input id="project-name" aria-invalid={!!errors.name} aria-describedby={describedBy("project-name", errors.name?.message)} {...form.register("name")} />
            </Field>
            <Field id="project-description" label="Description" error={errors.description?.message}>
              <Textarea id="project-description" rows={3} {...form.register("description")} />
            </Field>
          </fieldset>
          {canEdit ? (
            <div className="flex items-center gap-3">
              <Button type="submit" size="sm" disabled={save.isPending}>
                {save.isPending ? "Saving…" : "Save details"}
              </Button>
              {saved ? <span role="status" className="text-sm text-success">Saved</span> : null}
            </div>
          ) : null}
        </form>
      </CardContent>
    </Card>
  );
}

function DeleteCard({ project }: { project: Project }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const remove = useMutation({
    mutationFn: () => api<void>(`/projects/${project.id}`, { method: "DELETE" }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: keys.projects(project.organisation_id) });
      router.push("/projects");
    },
  });
  return (
    <Card className="border-destructive/30">
      <CardHeader>
        <CardTitle>Delete project</CardTitle>
        <CardDescription>
          The project is hidden from all users. Its history is kept for the audit trail.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {remove.error ? (
          <Alert variant="destructive">
            <AlertDescription>{(remove.error as Error).message}</AlertDescription>
          </Alert>
        ) : null}
        <Button
          variant="destructive"
          size="sm"
          disabled={remove.isPending}
          onClick={() => {
            if (window.confirm(`Delete project "${project.name}"?`)) remove.mutate();
          }}
        >
          <Trash2 aria-hidden /> Delete project
        </Button>
      </CardContent>
    </Card>
  );
}

const int = (min: number, max: number, label: string) =>
  z.number({ message: `${label} must be a number` }).int().min(min, `${label} must be at least ${min}`).max(max, `${label} must be at most ${max}`);

const settingsSchema = z.object({
  max_pages: int(1, 10000, "Max pages"),
  max_depth: int(0, 50, "Max depth"),
  concurrency: int(1, 20, "Concurrency"),
  timeout_seconds: int(1, 120, "Timeout"),
  delay_ms: int(0, 60000, "Delay"),
  user_agent: z.string().trim().min(3).max(300),
  render_javascript: z.boolean(),
  allowed_extra_hosts: z.string(),
  excluded_paths: z.string(),
  important_pages: z.string(),
  page_groups: z.string(),
  content_types: z.string(),
  description: z.string().max(5000),
  contact_email: z.union([z.literal(""), z.string().trim().email("Enter a valid email")]),
  contact_phone: z.string().max(50),
  contact_address: z.string().max(500),
  approved_sources: z.string(),
  editorial_approval_required: z.boolean(),
});
type SettingsValues = z.infer<typeof settingsSchema>;

function toForm(s: ProjectSettingsData): SettingsValues {
  return {
    ...s.crawl,
    allowed_extra_hosts: s.allowed_extra_hosts.join("\n"),
    excluded_paths: s.excluded_paths.join("\n"),
    important_pages: s.important_pages.join("\n"),
    page_groups: formatPageGroups(s.page_groups),
    content_types: formatContentTypes(s.content_types),
    description: s.institutional_profile.description ?? "",
    contact_email: s.institutional_profile.contact.email ?? "",
    contact_phone: s.institutional_profile.contact.phone ?? "",
    contact_address: s.institutional_profile.contact.address ?? "",
    approved_sources: formatSources(s.institutional_profile.approved_sources),
    editorial_approval_required: s.editorial_approval_required,
  };
}

function fromForm(v: SettingsValues): ProjectSettingsData {
  return {
    crawl: {
      max_pages: v.max_pages,
      max_depth: v.max_depth,
      concurrency: v.concurrency,
      timeout_seconds: v.timeout_seconds,
      delay_ms: v.delay_ms,
      user_agent: v.user_agent,
      render_javascript: v.render_javascript,
    },
    allowed_extra_hosts: splitLines(v.allowed_extra_hosts),
    excluded_paths: splitLines(v.excluded_paths),
    important_pages: splitLines(v.important_pages),
    page_groups: parsePageGroups(v.page_groups),
    content_types: parseContentTypes(v.content_types),
    institutional_profile: {
      description: v.description.trim() || null,
      contact: {
        email: v.contact_email || null,
        phone: v.contact_phone.trim() || null,
        address: v.contact_address.trim() || null,
      },
      approved_sources: parseSources(v.approved_sources),
    },
    editorial_approval_required: v.editorial_approval_required,
  };
}

const API_FIELDS: Record<string, keyof SettingsValues> = {
  "crawl.max_pages": "max_pages",
  "settings.crawl.max_pages": "max_pages",
  "crawl.max_depth": "max_depth",
  "settings.crawl.max_depth": "max_depth",
  "crawl.concurrency": "concurrency",
  "settings.crawl.concurrency": "concurrency",
  "crawl.timeout_seconds": "timeout_seconds",
  "crawl.delay_ms": "delay_ms",
  "crawl.user_agent": "user_agent",
  "institutional_profile.contact.email": "contact_email",
};

function SettingsForm({ project, settings, canEdit }: { project: Project; settings: ProjectSettings; canEdit: boolean }) {
  const queryClient = useQueryClient();
  const [saved, setSaved] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<SettingsValues>({ resolver: zodResolver(settingsSchema), defaultValues: toForm(settings.settings) });

  useEffect(() => form.reset(toForm(settings.settings)), [settings, form]);

  const save = useMutation({
    mutationFn: (values: SettingsValues) =>
      api<ProjectSettings>(`/projects/${project.id}/settings`, { method: "PUT", body: fromForm(values) }),
    onSuccess: (updated) => {
      queryClient.setQueryData(keys.projectSettings(project.id), updated);
      setSaved(true);
    },
    onError: (error) => setFormError(applyApiErrors(error, form.setError, API_FIELDS)),
  });

  const { errors } = form.formState;
  const num = (name: "max_pages" | "max_depth" | "concurrency" | "timeout_seconds" | "delay_ms", label: string, hint?: string) => (
    <Field id={name} label={label} error={errors[name]?.message} hint={hint}>
      <Input
        id={name}
        type="number"
        inputMode="numeric"
        aria-invalid={!!errors[name]}
        aria-describedby={describedBy(name, errors[name]?.message, hint)}
        {...form.register(name, { valueAsNumber: true })}
      />
    </Field>
  );
  const lines = (name: keyof SettingsValues, label: string, hint: string, rows = 3) => (
    <Field id={name} label={label} hint={hint} error={errors[name]?.message as string | undefined}>
      <Textarea id={name} rows={rows} className="font-mono text-xs" aria-describedby={`${name}-hint`} {...form.register(name)} />
    </Field>
  );

  return (
    <form
      noValidate
      className="space-y-6"
      onSubmit={form.handleSubmit((values) => {
        setSaved(false);
        setFormError(null);
        save.mutate(values);
      })}
    >
      {!canEdit ? (
        <Alert>
          <AlertDescription>Your role can view these settings but not change them.</AlertDescription>
        </Alert>
      ) : null}
      <fieldset disabled={!canEdit} className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Crawl settings</CardTitle>
            <CardDescription>Conservative defaults protect the website being crawled. robots.txt is always respected.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            {num("max_pages", "Maximum pages")}
            {num("max_depth", "Maximum depth", "Link hops from the root URL")}
            {num("concurrency", "Concurrent requests")}
            {num("timeout_seconds", "Request timeout (seconds)")}
            {num("delay_ms", "Delay between requests (ms)")}
            <Field id="user_agent" label="User agent" error={errors.user_agent?.message}>
              <Input id="user_agent" {...form.register("user_agent")} />
            </Field>
            <div className="flex items-center gap-2 sm:col-span-2">
              <input id="render_javascript" type="checkbox" className="size-4 accent-[var(--primary)]" {...form.register("render_javascript")} />
              <label htmlFor="render_javascript" className="text-sm">
                Render JavaScript with a headless browser (slower; only for sites that need it)
              </label>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Scope and priorities</CardTitle>
            <CardDescription>One entry per line.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {lines("allowed_extra_hosts", "Additional hosts to crawl", "Only hosts your organisation owns, e.g. admissions.example.org")}
            {lines("excluded_paths", "Excluded paths", "Path patterns starting with /, e.g. /wp-admin/*")}
            {lines("important_pages", "Important pages", "Paths or full URLs; issues on these pages are ranked higher")}
            {lines("page_groups", "Page groups", "Name | /pattern/*, /other/*")}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Content types</CardTitle>
            <CardDescription>
              Used to classify pages. Expected sections are reported as editorial suggestions, never as errors.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {lines("content_types", "Content types", "key | Label | /url-pattern/*, ... | expected section, ...", 9)}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Institutional profile</CardTitle>
            <CardDescription>
              Verified facts the AI assistant may rely on. Leave blank anything not yet confirmed.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <Field id="description" label="Institutional description">
                <Textarea id="description" rows={4} {...form.register("description")} />
              </Field>
            </div>
            <Field id="contact_email" label="Official contact email" error={errors.contact_email?.message}>
              <Input id="contact_email" type="email" aria-invalid={!!errors.contact_email} {...form.register("contact_email")} />
            </Field>
            <Field id="contact_phone" label="Official phone">
              <Input id="contact_phone" {...form.register("contact_phone")} />
            </Field>
            <div className="sm:col-span-2">
              <Field id="contact_address" label="Official address">
                <Textarea id="contact_address" rows={2} {...form.register("contact_address")} />
              </Field>
            </div>
            <div className="sm:col-span-2">
              {lines("approved_sources", "Approved content sources", "Label | https://url")}
            </div>
            <div className="flex items-center gap-2 sm:col-span-2">
              <input id="editorial_approval_required" type="checkbox" className="size-4" {...form.register("editorial_approval_required")} />
              <label htmlFor="editorial_approval_required" className="text-sm">
                Require human approval for every content draft
              </label>
            </div>
          </CardContent>
        </Card>
      </fieldset>

      {formError ? (
        <Alert variant="destructive">
          <AlertDescription>{formError}</AlertDescription>
        </Alert>
      ) : null}
      {canEdit ? (
        <div className="flex items-center gap-3">
          <Button type="submit" disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save settings"}
          </Button>
          {saved ? <span role="status" className="text-sm text-success">Settings saved</span> : null}
        </div>
      ) : null}
    </form>
  );
}
