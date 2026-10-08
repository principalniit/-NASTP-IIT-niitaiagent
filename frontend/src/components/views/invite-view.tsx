"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { Building2, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { describedBy, Field } from "@/components/app/field";
import { LoadingState } from "@/components/app/states";
import { AuthPanel, useHashToken } from "@/components/login/auth-panel";
import { MISMATCH, NewPasswordFields, passwordFields, passwordsMatch } from "@/components/views/password-reset-view";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, ApiError, signInErrorText } from "@/lib/api";
import { applyApiErrors } from "@/lib/form-errors";
import { useSession } from "@/lib/session";
import { ROLE_LABELS, type InvitationPreview } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

/**
 * Accept an invitation from its link. A new person creates their account here; someone
 * who already has an account signs in as that account and joins. The token stays in the
 * link's fragment and is sent only in request bodies.
 */
export function InviteView() {
  const token = useHashToken();
  const preview = useQuery({
    queryKey: ["invitation", token],
    queryFn: () => api<InvitationPreview>("/invitations/lookup", { method: "POST", body: { token } }),
    enabled: !!token,
    retry: false,
  });

  let body: React.ReactNode;
  if (token === undefined || (token && preview.isLoading)) {
    body = <LoadingState rows={2} label="Checking the invitation" />;
  } else if (!token || preview.error) {
    body = (
      <Alert variant="destructive">
        <AlertDescription>
          {!token
            ? "This page needs the link from your invitation."
            : preview.error instanceof ApiError && preview.error.status === 404
              ? "This invitation is not valid or has expired. Ask your administrator to send a new one."
              : "The invitation could not be checked right now. Please try again."}
        </AlertDescription>
      </Alert>
    );
  } else if (preview.data) {
    body = (
      <div className="space-y-6">
        <Summary invitation={preview.data} />
        {preview.data.account_exists ? (
          <JoinWithAccount token={token} invitation={preview.data} />
        ) : (
          <CreateAccount token={token} invitation={preview.data} onAccountExists={() => void preview.refetch()} />
        )}
      </div>
    );
  }
  return (
    <AuthPanel title="You're invited" description="Join your team on the SEO platform.">
      {body}
    </AuthPanel>
  );
}

function Summary({ invitation }: { invitation: InvitationPreview }) {
  return (
    <dl className="grid gap-3 rounded-xl border bg-muted/40 p-4 text-sm">
      <div className="flex items-center gap-3">
        <span className="flex size-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
          <Building2 className="size-4" aria-hidden />
        </span>
        <div>
          <dt className="sr-only">Organisation</dt>
          <dd className="font-semibold">{invitation.organisation_name}</dd>
          <dd className="text-muted-foreground">{invitation.email}</dd>
        </div>
      </div>
      <div className="flex flex-wrap gap-x-6 gap-y-1 text-muted-foreground">
        <div className="flex gap-1">
          <dt>Role:</dt>
          <dd className="font-medium text-foreground">{ROLE_LABELS[invitation.role]}</dd>
        </div>
        <div className="flex gap-1">
          <dt>Expires:</dt>
          <dd>{formatDateTime(invitation.expires_at)}</dd>
        </div>
      </div>
    </dl>
  );
}

const createSchema = z
  .object({ full_name: z.string().trim().min(1, "Enter your name").max(200, "At most 200 characters"), ...passwordFields })
  .refine(passwordsMatch, MISMATCH);
type CreateValues = z.infer<typeof createSchema>;

function CreateAccount({
  token,
  invitation,
  onAccountExists,
}: {
  token: string;
  invitation: InvitationPreview;
  onAccountExists: () => void;
}) {
  const router = useRouter();
  const { signIn } = useSession();
  const [error, setError] = useState<string | null>(null);
  const form = useForm<CreateValues>({
    resolver: zodResolver(createSchema),
    defaultValues: { full_name: "", password: "", confirm: "" },
  });
  const { errors, isSubmitting } = form.formState;

  const onSubmit = form.handleSubmit(async (v) => {
    setError(null);
    try {
      await api("/invitations/accept-new", {
        method: "POST",
        body: { token, full_name: v.full_name, password: v.password },
      });
    } catch (err) {
      if (err instanceof ApiError && err.code === "account_exists") return onAccountExists();
      setError(
        err instanceof ApiError && err.status === 404
          ? "This invitation is not valid or has expired. Ask your administrator to send a new one."
          : applyApiErrors(err, form.setError, { full_name: "full_name", password: "password" }),
      );
      return;
    }
    try {
      await signIn(invitation.email, v.password);
      router.replace("/overview");
    } catch {
      router.replace("/login");
    }
  });

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-4" aria-label="Create your account">
      <p className="text-sm text-muted-foreground">Create your account to accept. You will sign in with {invitation.email}.</p>
      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      <Field id="invite-name" label="Your name" error={errors.full_name?.message}>
        <Input
          id="invite-name"
          autoComplete="name"
          aria-invalid={!!errors.full_name}
          aria-describedby={describedBy("invite-name", errors.full_name?.message)}
          {...form.register("full_name")}
        />
      </Field>
      <NewPasswordFields form={form} idPrefix="invite" />
      <Button type="submit" className="w-full" disabled={isSubmitting}>
        {isSubmitting ? "Creating your account…" : "Create account and join"}
      </Button>
    </form>
  );
}

const signInSchema = z.object({ password: z.string().min(1, "Enter your password") });

function JoinWithAccount({ token, invitation }: { token: string; invitation: InvitationPreview }) {
  const router = useRouter();
  const { status, me, signIn, signOut, reload } = useSession();
  const [error, setError] = useState<string | null>(null);
  const [joining, setJoining] = useState(false);
  const form = useForm<z.infer<typeof signInSchema>>({ resolver: zodResolver(signInSchema), defaultValues: { password: "" } });

  const join = async () => {
    setError(null);
    setJoining(true);
    try {
      await api("/invitations/accept", { method: "POST", body: { token } });
      await reload();
      router.replace("/overview");
    } catch (err) {
      setJoining(false);
      setError(err instanceof ApiError ? err.message : "The invitation could not be accepted. Please try again.");
    }
  };

  const onSignIn = form.handleSubmit(async ({ password }) => {
    setError(null);
    try {
      await signIn(invitation.email, password);
    } catch (err) {
      setError(signInErrorText(err));
      return;
    }
    await join();
  });

  if (status === "loading") return <LoadingState rows={1} />;
  const errorAlert = error ? (
    <Alert variant="destructive">
      <AlertDescription>{error}</AlertDescription>
    </Alert>
  ) : null;

  if (status === "authenticated" && me) {
    if (me.user.email.toLowerCase() !== invitation.email) {
      return (
        <div className="space-y-4">
          <Alert>
            <AlertDescription>
              You are signed in as {me.user.email}, but this invitation is for {invitation.email}. Sign out, then sign
              in with the invited address.
            </AlertDescription>
          </Alert>
          <Button variant="outline" className="w-full" onClick={() => void signOut()}>
            Sign out
          </Button>
        </div>
      );
    }
    return (
      <div className="space-y-4">
        {errorAlert}
        <Button className="w-full" disabled={joining} onClick={() => void join()}>
          <ShieldCheck aria-hidden /> {joining ? "Joining…" : `Join ${invitation.organisation_name}`}
        </Button>
      </div>
    );
  }

  const { errors, isSubmitting } = form.formState;
  return (
    <form onSubmit={onSignIn} noValidate className="space-y-4" aria-label="Sign in to accept">
      <p className="text-sm text-muted-foreground">
        {invitation.email} already has an account. Sign in to accept the invitation.
      </p>
      {errorAlert}
      <Field id="invite-signin-password" label="Password" error={errors.password?.message}>
        <Input
          id="invite-signin-password"
          type="password"
          autoComplete="current-password"
          aria-invalid={!!errors.password}
          aria-describedby={describedBy("invite-signin-password", errors.password?.message)}
          {...form.register("password")}
        />
      </Field>
      <Button type="submit" className="w-full" disabled={isSubmitting || joining}>
        {isSubmitting || joining ? "Joining…" : "Sign in and join"}
      </Button>
      <p className="text-sm">
        <Link href="/forgot-password" className="text-primary underline-offset-4 hover:underline">
          Forgot your password?
        </Link>
      </p>
    </form>
  );
}
