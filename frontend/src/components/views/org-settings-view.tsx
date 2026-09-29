"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { describedBy, Field } from "@/components/app/field";
import { NoOrganisation } from "@/components/app/no-organisation";
import { PageHeader } from "@/components/app/page-header";
import { LoadingState } from "@/components/app/states";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { useCurrentOrg } from "@/lib/current-org";
import { applyApiErrors } from "@/lib/form-errors";
import { formatTerminology, parseTerminology } from "@/lib/line-formats";
import { keys } from "@/lib/queries";
import type { Organisation } from "@/lib/types";

const int = (min: number, max: number) => z.number({ message: "Enter a number" }).int().min(min).max(max);

const schema = z.object({
  name: z.string().trim().min(1, "Enter a name").max(200),
  domain: z.string().trim().max(253),
  logo_url: z.union([z.literal(""), z.string().trim().url("Enter a full https URL").startsWith("https://", "Logo must use https")]),
  timezone: z.string().trim().min(1, "Enter a time zone"),
  language: z.string().trim().regex(/^[a-z]{2,3}(-[A-Z]{2})?$/, "Use a code such as en or ur"),
  brand_tone: z.string().max(1000),
  terminology: z.string(),
  ai_provider: z.enum(["none", "ollama"]),
  ai_model: z.string().max(100),
  max_pages: int(1, 10000),
  max_depth: int(0, 50),
  max_concurrency: int(1, 20),
  primary_colour: z.union([z.literal(""), z.string().regex(/^#[0-9a-fA-F]{6}$/, "Use a hex colour such as #1f3a8a")]),
  footer_text: z.string().max(300),
});
type Values = z.infer<typeof schema>;

function toForm(org: Organisation): Values {
  const s = org.settings;
  return {
    name: org.name,
    domain: org.domain ?? "",
    logo_url: org.logo_url ?? "",
    timezone: org.timezone,
    language: org.language,
    brand_tone: s.brand_tone ?? "",
    terminology: formatTerminology(s.approved_terminology),
    ai_provider: s.ai.provider,
    ai_model: s.ai.model ?? "",
    max_pages: s.crawl_limits.max_pages,
    max_depth: s.crawl_limits.max_depth,
    max_concurrency: s.crawl_limits.max_concurrency,
    primary_colour: s.report_branding.primary_colour ?? "",
    footer_text: s.report_branding.footer_text ?? "",
  };
}

const API_FIELDS: Record<string, keyof Values> = {
  name: "name",
  domain: "domain",
  logo_url: "logo_url",
  timezone: "timezone",
  language: "language",
  "settings.brand_tone": "brand_tone",
  "settings.report_branding.primary_colour": "primary_colour",
};

export function OrgSettingsView() {
  const { current, can, isLoading } = useCurrentOrg();
  if (isLoading) return <LoadingState />;
  if (!current) return <NoOrganisation />;
  return <OrgSettingsForm key={current.id} org={current} canEdit={can("org:update")} />;
}

function OrgSettingsForm({ org, canEdit }: { org: Organisation; canEdit: boolean }) {
  const queryClient = useQueryClient();
  const [saved, setSaved] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: toForm(org) });
  useEffect(() => form.reset(toForm(org)), [org, form]);

  const save = useMutation({
    mutationFn: (v: Values) =>
      api<Organisation>(`/organisations/${org.id}`, {
        method: "PATCH",
        body: {
          name: v.name,
          domain: v.domain || null,
          logo_url: v.logo_url || null,
          timezone: v.timezone,
          language: v.language,
          settings: {
            ...org.settings,
            brand_tone: v.brand_tone.trim() || null,
            approved_terminology: parseTerminology(v.terminology),
            ai: { provider: v.ai_provider, model: v.ai_model.trim() || null },
            crawl_limits: { max_pages: v.max_pages, max_depth: v.max_depth, max_concurrency: v.max_concurrency },
            report_branding: { primary_colour: v.primary_colour || null, footer_text: v.footer_text.trim() || null },
          },
        },
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: keys.organisations });
      setSaved(true);
    },
    onError: (error) => setFormError(applyApiErrors(error, form.setError, API_FIELDS)),
  });

  const { errors } = form.formState;
  const text = (name: keyof Values, label: string, hint?: string, type = "text") => (
    <Field id={name} label={label} hint={hint} error={errors[name]?.message}>
      <Input
        id={name}
        type={type}
        aria-invalid={!!errors[name]}
        aria-describedby={describedBy(name, errors[name]?.message, hint)}
        {...form.register(name, { valueAsNumber: type === "number" })}
      />
    </Field>
  );

  return (
    <>
      <PageHeader title="Settings" description={`Organisation-level configuration for ${org.name}.`} />
      <form
        noValidate
        className="max-w-3xl space-y-6"
        onSubmit={form.handleSubmit((v) => {
          setSaved(false);
          setFormError(null);
          save.mutate(v);
        })}
      >
        {!canEdit ? (
          <Alert>
            <AlertDescription>Only owners and administrators can change organisation settings.</AlertDescription>
          </Alert>
        ) : null}
        <fieldset disabled={!canEdit} className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Organisation</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2">
              {text("name", "Name")}
              {text("domain", "Website domain", "e.g. niit.edu.pk")}
              {text("timezone", "Time zone", "IANA name, e.g. Asia/Karachi")}
              {text("language", "Preferred language", "e.g. en")}
              <div className="sm:col-span-2">{text("logo_url", "Logo URL", "An https image URL used in reports")}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Brand voice and terminology</CardTitle>
              <CardDescription>Guides AI drafts. It never overrides verified institutional facts.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Field id="brand_tone" label="Brand tone">
                <Textarea id="brand_tone" rows={3} {...form.register("brand_tone")} />
              </Field>
              <Field id="terminology" label="Approved terminology" hint="Preferred term | terms to avoid, comma separated | note">
                <Textarea id="terminology" rows={4} className="font-mono text-xs" aria-describedby="terminology-hint" {...form.register("terminology")} />
              </Field>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>AI provider</CardTitle>
              <CardDescription>AI features arrive in Phase 4. Everything else works with AI disabled.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2">
              <Field id="ai_provider" label="Provider">
                <NativeSelect id="ai_provider" {...form.register("ai_provider")}>
                  <option value="none">None</option>
                  <option value="ollama">Ollama (local)</option>
                </NativeSelect>
              </Field>
              {text("ai_model", "Model name", "As pulled in Ollama")}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Crawl limits</CardTitle>
              <CardDescription>Ceilings that no project in this organisation can exceed.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-3">
              {text("max_pages", "Max pages per crawl", undefined, "number")}
              {text("max_depth", "Max depth", undefined, "number")}
              {text("max_concurrency", "Max concurrency", undefined, "number")}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Report branding</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2">
              {text("primary_colour", "Primary colour", "Hex, e.g. #1f3a8a")}
              {text("footer_text", "Footer text")}
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
    </>
  );
}
