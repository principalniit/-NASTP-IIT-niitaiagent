"use client";

import Link from "next/link";
import { useSyncExternalStore } from "react";

import { BrandMark } from "@/components/app/brand-mark";

/** The frame for public account pages: invitations and password resets. */
export function AuthPanel({ title, description, children }: { title: string; description?: string; children: React.ReactNode }) {
  return (
    <main className="relative isolate flex min-h-screen items-center justify-center overflow-hidden bg-background px-4 py-12">
      <div className="pointer-events-none absolute -right-24 -top-24 -z-10 size-96 rounded-full bg-brand-violet/10 blur-3xl" aria-hidden />
      <div className="pointer-events-none absolute -bottom-32 -left-16 -z-10 size-80 rounded-full bg-brand-glow/10 blur-3xl" aria-hidden />
      <div className="w-full max-w-md animate-fade-up rounded-2xl border bg-card p-6 shadow-sm sm:p-8">
        <div className="mb-6 space-y-2">
          <BrandMark className="size-10" />
          <h1 className="pt-2 text-2xl font-semibold tracking-tight">{title}</h1>
          {description ? <p className="text-sm text-muted-foreground">{description}</p> : null}
        </div>
        {children}
        <p className="mt-8 text-sm">
          <Link href="/login" className="text-primary underline-offset-4 hover:underline">
            Back to sign in
          </Link>
        </p>
      </div>
    </main>
  );
}

/** The token from a link's fragment (`#token=...`), which browsers never send to a server. */
export function tokenFromHash(hash: string): string | null {
  const value = new URLSearchParams(hash.replace(/^#/, "")).get("token");
  return value && /^[\w-]{20,200}$/.test(value) ? value : null;
}

function subscribe(onChange: () => void) {
  window.addEventListener("hashchange", onChange);
  return () => window.removeEventListener("hashchange", onChange);
}

/** The link's token, or undefined while the page is still loading in the browser. */
export function useHashToken(): string | null | undefined {
  const hash = useSyncExternalStore(
    subscribe,
    () => window.location.hash,
    () => undefined,
  );
  return hash === undefined ? undefined : tokenFromHash(hash);
}
