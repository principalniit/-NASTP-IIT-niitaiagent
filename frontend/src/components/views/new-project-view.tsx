"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { describedBy, Field } from "@/components/app/field";
import { NoOrganisation } from "@/components/app/no-organisation";
import { PageHeader } from "@/components/app/page-header";
import { EmptyState, LoadingState } from "@/components/app/states";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { useCurrentOrg } from "@/lib/current-org";
import { applyApiErrors } from "@/lib/form-errors";
import { keys } from "@/lib/queries";
import type { Project } from "@/lib/types";

const schema = z.object({
  name: z.string().trim().min(1, "Enter a project name").max(200),
  root_url: z
    .string()
    .trim()
    .min(1, "Enter the website address")
    .max(2048)
    .refine((v) => !/^[a-z]+:\/\//i.test(v) || /^https?:\/\//i.test(v), "Use an http or https address"),
  description: z.string().max(2000).optional(),
});
type FormValues = z.infer<typeof schema>;

export function NewProjectView() {
  const { current, can, isLoading } = useCurrentOrg();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [formError, setFormError] = useState<string | null>(null);
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", root_url: "", description: "" },
  });
  const create = useMutation({
    mutationFn: (values: FormValues) =>
      api<Project>(`/organisations/${current?.id}/projects`, {
        method: "POST",
        body: { ...values, description: values.description || null },
      }),
    onSuccess: async (project) => {
      await queryClient.invalidateQueries({ queryKey: keys.projects(project.organisation_id) });
      router.push(`/projects/${project.id}`);
    },
    onError: (error) => {
      setFormError(
        applyApiErrors(error, form.setError, {
          name: "name",
          root_url: "root_url",
          description: "description",
        }),
      );
    },
  });

  if (isLoading) return <LoadingState />;
  if (!current) return <NoOrganisation />;
  if (!can("projects:create")) {
    return <EmptyState title="You cannot create projects" description="Only owners and administrators can add projects." />;
  }

  const { errors } = form.formState;
  return (
    <>
      <PageHeader title="New project" description={`Add a website to ${current.name}.`} />
      <Card className="max-w-2xl">
        <CardContent className="pt-5">
          <form
            noValidate
            className="space-y-5"
            onSubmit={form.handleSubmit((values) => {
              setFormError(null);
              create.mutate(values);
            })}
          >
            {formError ? (
              <Alert variant="destructive">
                <AlertDescription>{formError}</AlertDescription>
              </Alert>
            ) : null}
            <Field id="name" label="Project name" error={errors.name?.message}>
              <Input id="name" aria-invalid={!!errors.name} aria-describedby={describedBy("name", errors.name?.message)} {...form.register("name")} />
            </Field>
            <Field
              id="root_url"
              label="Website address"
              error={errors.root_url?.message}
              hint="For example https://niit.edu.pk. Local and private network addresses are rejected."
            >
              <Input
                id="root_url"
                inputMode="url"
                placeholder="https://"
                aria-invalid={!!errors.root_url}
                aria-describedby={describedBy("root_url", errors.root_url?.message, "hint")}
                {...form.register("root_url")}
              />
            </Field>
            <Field id="description" label="Description (optional)" error={errors.description?.message}>
              <Textarea id="description" rows={3} {...form.register("description")} />
            </Field>
            <div className="flex gap-2">
              <Button type="submit" disabled={create.isPending}>
                {create.isPending ? "Creating…" : "Create project"}
              </Button>
              <Button variant="outline" asChild>
                <Link href="/projects">Cancel</Link>
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </>
  );
}
