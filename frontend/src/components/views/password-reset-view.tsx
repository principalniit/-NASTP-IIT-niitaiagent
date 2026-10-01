"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, MailQuestion } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useForm, type FieldErrors, type Path, type UseFormReturn } from "react-hook-form";
import { z } from "zod";

import { describedBy, Field } from "@/components/app/field";
import { LoadingState } from "@/components/app/states";
import { AuthPanel, useHashToken } from "@/components/login/auth-panel";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";
import { applyApiErrors } from "@/lib/form-errors";

const requestSchema = z.object({ email: z.string().trim().min(1, "Enter your email").email("Enter a valid email address") });

export function ForgotPasswordView() {
  const available = useQuery({
    queryKey: ["password-reset", "available"],
    queryFn: () => api<{ email_enabled: boolean }>("/auth/password-reset/available"),
  });
  const [sent, setSent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const form = useForm<z.infer<typeof requestSchema>>({ resolver: zodResolver(requestSchema), defaultValues: { email: "" } });
  const { errors, isSubmitting } = form.formState;

  const onSubmit = form.handleSubmit(async ({ email }) => {
    setError(null);
    try {
      const result = await api<{ detail: string }>("/auth/password-reset/request", { method: "POST", body: { email } });
      setSent(result.detail);
    } catch {
      setError("The request could not be sent right now. Please try again.");
    }
  });

  return (
    <AuthPanel title="Forgot your password?" description="We will email you a link to choose a new one.">
      {available.isLoading ? (
        <LoadingState rows={2} />
      ) : available.data && !available.data.email_enabled ? (
        <Alert>
          <MailQuestion className="size-4" aria-hidden />
          <AlertDescription>
            Email is not set up on this server, so reset links cannot be sent. Ask your organisation&apos;s administrator
            or the platform operator to reset your password.
          </AlertDescription>
        </Alert>
      ) : sent ? (
        <Alert>
          <CheckCircle2 className="size-4" aria-hidden />
          <AlertDescription role="status">{sent} The link expires soon and works once.</AlertDescription>
        </Alert>
      ) : (
        <form onSubmit={onSubmit} noValidate className="space-y-4">
          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}
          <Field id="reset-email" label="Email" error={errors.email?.message}>
            <Input
              id="reset-email"
              type="email"
              autoComplete="username"
              aria-invalid={!!errors.email}
              aria-describedby={describedBy("reset-email", errors.email?.message)}
              {...form.register("email")}
            />
          </Field>
          <Button type="submit" className="w-full" disabled={isSubmitting}>
            {isSubmitting ? "Sending…" : "Send reset link"}
          </Button>
        </form>
      )}
    </AuthPanel>
  );
}

export const passwordFields = {
  password: z.string().min(12, "At least 12 characters").max(128, "At most 128 characters"),
  confirm: z.string(),
};

export function passwordsMatch(v: { password: string; confirm: string }) {
  return v.password === v.confirm;
}
export const MISMATCH = { path: ["confirm"], message: "The passwords do not match" };

const newPasswordSchema = z.object(passwordFields).refine(passwordsMatch, MISMATCH);
type PasswordValues = { password: string; confirm: string };

export function NewPasswordFields<T extends PasswordValues>({ form, idPrefix }: { form: UseFormReturn<T>; idPrefix: string }) {
  const errors = form.formState.errors as FieldErrors<PasswordValues>;
  return (
    <>
      <Field id={`${idPrefix}-password`} label="New password" error={errors.password?.message} hint="At least 12 characters.">
        <Input
          id={`${idPrefix}-password`}
          type="password"
          autoComplete="new-password"
          aria-invalid={!!errors.password}
          aria-describedby={describedBy(`${idPrefix}-password`, errors.password?.message, "hint")}
          {...form.register("password" as Path<T>)}
        />
      </Field>
      <Field id={`${idPrefix}-confirm`} label="Confirm password" error={errors.confirm?.message}>
        <Input
          id={`${idPrefix}-confirm`}
          type="password"
          autoComplete="new-password"
          aria-invalid={!!errors.confirm}
          aria-describedby={describedBy(`${idPrefix}-confirm`, errors.confirm?.message)}
          {...form.register("confirm" as Path<T>)}
        />
      </Field>
    </>
  );
}

export function ResetPasswordView() {
  const token = useHashToken();
  const [done, setDone] = useState(false);
  const [expired, setExpired] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const form = useForm<PasswordValues>({
    resolver: zodResolver(newPasswordSchema),
    defaultValues: { password: "", confirm: "" },
  });

  const onSubmit = form.handleSubmit(async ({ password }) => {
    setError(null);
    try {
      await api<void>("/auth/password-reset/confirm", { method: "POST", body: { token, new_password: password } });
      setDone(true);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) setExpired(true);
      else setError(applyApiErrors(err, form.setError, { new_password: "password" }));
    }
  });

  return (
    <AuthPanel title="Choose a new password" description="Signing in again is required on every device afterwards.">
      {token === undefined ? (
        <LoadingState rows={2} />
      ) : token === null || expired ? (
        <Alert variant="destructive">
          <AlertDescription>
            {expired ? "This reset link is not valid or has expired." : "This page needs the link from your reset email."}{" "}
            <Link href="/forgot-password" className="underline underline-offset-4">
              Request a new link
            </Link>
            .
          </AlertDescription>
        </Alert>
      ) : done ? (
        <Alert>
          <CheckCircle2 className="size-4" aria-hidden />
          <AlertDescription role="status">
            Your password has been changed.{" "}
            <Link href="/login" className="underline underline-offset-4">
              Sign in
            </Link>{" "}
            with the new password.
          </AlertDescription>
        </Alert>
      ) : (
        <form onSubmit={onSubmit} noValidate className="space-y-4">
          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}
          <NewPasswordFields form={form} idPrefix="reset" />
          <Button type="submit" className="w-full" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting ? "Saving…" : "Set new password"}
          </Button>
        </form>
      )}
    </AuthPanel>
  );
}
