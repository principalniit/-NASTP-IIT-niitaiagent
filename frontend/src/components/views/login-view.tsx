"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowRight, Eye, EyeOff, ListChecks, LockKeyhole, Mail, Radar, ShieldCheck } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { BrandMark } from "@/components/app/brand-mark";
import { SeoHeroScene } from "@/components/login/seo-hero-scene";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api";
import { useSession } from "@/lib/session";

const schema = z.object({
  email: z.string().trim().min(1, "Enter your email").email("Enter a valid email address"),
  password: z.string().min(1, "Enter your password"),
});
type FormValues = z.infer<typeof schema>;

function safeNext(value: string | null): string {
  // Only allow paths on this site, to avoid open redirects. Browsers read "/\\host" and
  // paths with tabs or newlines as other sites, so the value is resolved the way a browser
  // would, and anything that leaves this origin is refused.
  if (!value || !value.startsWith("/") || /[\\\u0000-\u001f]/.test(value)) return "/overview";
  const base = "https://this.site";
  try {
    const url = new URL(value, base);
    const path = url.pathname + url.search + url.hash;
    return url.origin === base && !path.startsWith("//") ? path : "/overview";
  } catch {
    return "/overview";
  }
}

export function LoginView() {
  const { status, signIn } = useSession();
  const router = useRouter();
  const next = safeNext(useSearchParams().get("next"));
  const [error, setError] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const form = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { email: "", password: "" } });

  useEffect(() => {
    if (status === "authenticated") router.replace(next);
  }, [status, router, next]);

  const onSubmit = form.handleSubmit(async (values) => {
    setError(null);
    try {
      await signIn(values.email, values.password);
    } catch (err) {
      setError(
        err instanceof ApiError && (err.status === 401 || err.status === 429)
          ? err.message
          : "Sign-in is unavailable right now. Please try again.",
      );
    }
  });

  const { errors, isSubmitting } = form.formState;
  return (
    <main className="grid min-h-screen bg-background lg:grid-cols-[1.1fr_1fr]">
      <section
        aria-label="About the platform"
        className="relative isolate flex min-h-72 flex-col overflow-hidden bg-brand-gradient px-6 py-8 text-white sm:px-10 lg:min-h-screen lg:py-12"
      >
        <div className="relative z-10 flex items-center gap-3">
          <BrandMark className="size-9" />
          <span className="text-sm font-semibold tracking-wide text-white/90">AI SEO Agent</span>
        </div>
        <div className="pointer-events-none absolute inset-0 -z-0 flex items-center justify-center opacity-25 lg:static lg:my-4 lg:flex-1 lg:opacity-100">
          <SeoHeroScene className="max-h-[36rem] max-w-[36rem]" />
        </div>
        <div className="relative z-10 mt-auto max-w-lg space-y-4 animate-fade-up">
          <p className="text-3xl font-semibold leading-tight tracking-tight sm:text-4xl">
            Search visibility, <span className="text-gradient">engineered with AI</span>
          </p>
          <ul className="grid gap-2 text-sm text-white/80 sm:grid-cols-3 sm:gap-4">
            <li className="flex items-start gap-2">
              <Radar className="mt-0.5 size-4 shrink-0 text-brand-teal" aria-hidden />
              Safe crawling that respects robots.txt
            </li>
            <li className="flex items-start gap-2">
              <ListChecks className="mt-0.5 size-4 shrink-0 text-brand-teal" aria-hidden />
              Rule-based checks, each with evidence
            </li>
            <li className="flex items-start gap-2">
              <ShieldCheck className="mt-0.5 size-4 shrink-0 text-brand-teal" aria-hidden />
              Local AI drafts, approved by people
            </li>
          </ul>
        </div>
      </section>

      <section className="relative isolate flex items-center justify-center overflow-hidden px-4 py-12 sm:px-8">
        <div className="pointer-events-none absolute -right-24 -top-24 -z-10 size-96 rounded-full bg-brand-violet/10 blur-3xl" aria-hidden />
        <div className="pointer-events-none absolute -bottom-32 -left-16 -z-10 size-80 rounded-full bg-brand-glow/10 blur-3xl" aria-hidden />
        <div className="w-full max-w-sm animate-fade-up" style={{ animationDelay: "0.1s" }}>
          <div className="mb-8 space-y-2">
            <BrandMark className="size-11" />
            <h1 className="pt-2 text-2xl font-semibold tracking-tight">NIIT AI SEO Agent</h1>
            <p className="text-sm text-muted-foreground">Sign in to manage search visibility for your organisation.</p>
          </div>
          <form onSubmit={onSubmit} noValidate className="space-y-4">
            {error ? (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            ) : null}
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <div className="relative">
                <Mail className="pointer-events-none absolute left-3 top-2.5 size-4 text-muted-foreground" aria-hidden />
                <Input
                  id="email"
                  type="email"
                  autoComplete="username"
                  className="h-10 pl-9"
                  aria-invalid={!!errors.email}
                  aria-describedby={errors.email ? "email-error" : undefined}
                  {...form.register("email")}
                />
              </div>
              {errors.email ? (
                <p id="email-error" className="text-sm text-destructive">
                  {errors.email.message}
                </p>
              ) : null}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">Password</Label>
              <div className="relative">
                <LockKeyhole className="pointer-events-none absolute left-3 top-2.5 size-4 text-muted-foreground" aria-hidden />
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  className="h-10 px-9"
                  aria-invalid={!!errors.password}
                  aria-describedby={errors.password ? "password-error" : undefined}
                  {...form.register("password")}
                />
                <button
                  type="button"
                  className="absolute right-2 top-2 rounded p-0.5 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? "Hide characters" : "Show characters"}
                  aria-pressed={showPassword}
                >
                  {showPassword ? <EyeOff className="size-4" aria-hidden /> : <Eye className="size-4" aria-hidden />}
                </button>
              </div>
              {errors.password ? (
                <p id="password-error" className="text-sm text-destructive">
                  {errors.password.message}
                </p>
              ) : null}
            </div>
            <Button
              type="submit"
              className="h-10 w-full bg-gradient-to-r from-brand-violet to-brand-glow text-white shadow-lg shadow-brand-violet/25 transition-[transform,box-shadow] hover:-translate-y-px hover:shadow-xl hover:shadow-brand-violet/30"
              disabled={isSubmitting}
            >
              {isSubmitting ? "Signing in…" : "Sign in"}
              {isSubmitting ? null : <ArrowRight aria-hidden />}
            </Button>
          </form>
          <p className="mt-8 text-xs text-muted-foreground">
            Accounts are created by your organisation&apos;s administrators. Nothing on your website changes without a
            person&apos;s approval.
          </p>
        </div>
      </section>
    </main>
  );
}
