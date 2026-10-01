"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, MailCheck, Send } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { describedBy, Field } from "@/components/app/field";
import { ErrorState, LoadingState } from "@/components/app/states";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, ApiError } from "@/lib/api";
import { applyApiErrors } from "@/lib/form-errors";
import { keys, useInvitations } from "@/lib/queries";
import { ROLE_LABELS, type Invitation, type InvitationCreated, type Organisation, type OrgRole } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

const ROLES = Object.keys(ROLE_LABELS) as OrgRole[];

const schema = z.object({
  email: z.string().trim().email("Enter a valid email address"),
  role: z.enum(["owner", "admin", "seo_manager", "editor", "viewer"]),
});
type Values = z.infer<typeof schema>;

/**
 * Invite people by email. The person accepts from the link: a new person creates their own
 * account and password, and someone with an account signs in. The link is shown once, so it
 * can be shared by hand when the server has no mail set up.
 */
export function InvitationsCard({ org, ownerLevel }: { org: Organisation; ownerLevel: boolean }) {
  const queryClient = useQueryClient();
  const invitations = useInvitations(org.id);
  const [created, setCreated] = useState<InvitationCreated | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { email: "", role: "viewer" } });
  const invalidate = () => queryClient.invalidateQueries({ queryKey: keys.invitations(org.id) });

  const invite = useMutation({
    mutationFn: (v: Values) =>
      api<InvitationCreated>(`/organisations/${org.id}/invitations`, { method: "POST", body: v }),
    onSuccess: (result) => {
      setCreated(result);
      setCopied(false);
      form.reset({ email: "", role: form.getValues("role") });
      void invalidate();
    },
    onError: (error) => setFormError(applyApiErrors(error, form.setError, { email: "email", role: "role" })),
  });
  const revoke = useMutation({
    mutationFn: (invitation: Invitation) =>
      api<void>(`/organisations/${org.id}/invitations/${invitation.id}`, { method: "DELETE" }),
    onSuccess: () => void invalidate(),
    onError: (e) => setActionError(e instanceof ApiError ? e.message : "Could not cancel the invitation"),
  });

  const copy = async () => {
    if (!created) return;
    try {
      await navigator.clipboard.writeText(created.invite_url);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  const { errors } = form.formState;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Invitations</CardTitle>
        <CardDescription>
          Invite people by email. New people choose their own password; people who already have an account accept by
          signing in.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form
          noValidate
          aria-label="Invite a member"
          className="grid gap-4 rounded-lg border bg-muted/30 p-4 sm:grid-cols-[1fr_12rem_auto] sm:items-end"
          onSubmit={form.handleSubmit((v) => {
            setFormError(null);
            invite.mutate(v);
          })}
        >
          <Field id="invite-email" label="Email to invite" error={errors.email?.message}>
            <Input
              id="invite-email"
              type="email"
              aria-invalid={!!errors.email}
              aria-describedby={describedBy("invite-email", errors.email?.message)}
              {...form.register("email")}
            />
          </Field>
          <Field id="invite-role" label="Role">
            <NativeSelect id="invite-role" {...form.register("role")}>
              {ROLES.filter((r) => ownerLevel || r !== "owner").map((r) => (
                <option key={r} value={r}>
                  {ROLE_LABELS[r]}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <Button type="submit" disabled={invite.isPending}>
            <Send aria-hidden /> {invite.isPending ? "Sending…" : "Send invitation"}
          </Button>
        </form>

        {formError ? (
          <Alert variant="destructive">
            <AlertDescription>{formError}</AlertDescription>
          </Alert>
        ) : null}

        {created ? (
          <Alert className="animate-fade-up">
            <MailCheck className="size-4" aria-hidden />
            <AlertDescription className="space-y-3">
              <p role="status">
                {created.email_sent
                  ? `Invitation emailed to ${created.invitation.email}.`
                  : `Invitation created for ${created.invitation.email}. Email is not set up on this server, so share this link with them yourself.`}{" "}
                The link works once and expires on {formatDateTime(created.invitation.expires_at)}. It is shown only now.
              </p>
              <div className="flex flex-col gap-2 sm:flex-row">
                <label htmlFor="invite-link" className="sr-only">
                  Invitation link
                </label>
                <Input id="invite-link" readOnly value={created.invite_url} className="font-mono text-xs" onFocus={(e) => e.currentTarget.select()} />
                <Button type="button" variant="outline" onClick={() => void copy()}>
                  {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
                  {copied ? "Copied" : "Copy link"}
                </Button>
              </div>
            </AlertDescription>
          </Alert>
        ) : null}

        {actionError ? (
          <Alert variant="destructive">
            <AlertDescription>{actionError}</AlertDescription>
          </Alert>
        ) : null}

        {invitations.isLoading ? (
          <LoadingState rows={2} />
        ) : invitations.error ? (
          <ErrorState error={invitations.error} onRetry={() => void invitations.refetch()} />
        ) : !invitations.data?.length ? (
          <p className="text-sm text-muted-foreground">No pending invitations.</p>
        ) : (
          <Table aria-label="Pending invitations">
            <TableHeader>
              <TableRow>
                <TableHead>Email</TableHead>
                <TableHead>Role</TableHead>
                <TableHead className="hidden sm:table-cell">Expires</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {invitations.data.map((inv) => {
                const locked = !ownerLevel && inv.role === "owner";
                return (
                  <TableRow key={inv.id}>
                    <TableCell className="font-medium">{inv.email}</TableCell>
                    <TableCell>{ROLE_LABELS[inv.role]}</TableCell>
                    <TableCell className="hidden text-muted-foreground sm:table-cell">{formatDateTime(inv.expires_at)}</TableCell>
                    <TableCell className="text-right">
                      {!locked ? (
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={revoke.isPending}
                          onClick={() => {
                            setActionError(null);
                            if (window.confirm(`Cancel the invitation for ${inv.email}?`)) revoke.mutate(inv);
                          }}
                        >
                          Cancel<span className="sr-only"> invitation for {inv.email}</span>
                        </Button>
                      ) : null}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
