"use client";

import { LogOut, Menu, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { BrandMark } from "@/components/app/brand-mark";
import { LoadingState } from "@/components/app/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import { CurrentOrgProvider, useCurrentOrg } from "@/lib/current-org";
import { NAV_GROUPS, NAV_ITEMS } from "@/lib/navigation";
import { useSession } from "@/lib/session";
import { ROLE_LABELS } from "@/lib/types";
import { cn } from "@/lib/utils";

export function AppShell({ children }: { children: React.ReactNode }) {
  const { status } = useSession();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (status === "anonymous") {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [status, router, pathname]);

  if (status !== "authenticated") {
    return (
      <div className="mx-auto mt-24 max-w-sm px-6">
        <LoadingState rows={2} label="Checking your session" />
      </div>
    );
  }
  return (
    <CurrentOrgProvider>
      <Shell>{children}</Shell>
    </CurrentOrgProvider>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const pathname = usePathname();

  return (
    <div className="flex min-h-screen">
      <a
        href="#main"
        className="sr-only z-50 rounded bg-primary px-3 py-2 text-primary-foreground focus:not-sr-only focus:fixed focus:left-3 focus:top-3"
      >
        Skip to main content
      </a>
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex w-64 -translate-x-full flex-col bg-sidebar text-sidebar-foreground transition-transform md:sticky md:top-0 md:h-screen md:translate-x-0",
          menuOpen && "translate-x-0",
        )}
        style={{
          backgroundImage:
            "radial-gradient(circle at 0% 0%, color-mix(in oklch, var(--brand-violet) 22%, transparent), transparent 55%), radial-gradient(circle at 100% 100%, color-mix(in oklch, var(--brand-glow) 14%, transparent), transparent 50%)",
        }}
      >
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-white/10 px-4">
          <Link href="/overview" className="flex items-center gap-2.5 font-semibold tracking-tight">
            <BrandMark className="size-7" />
            <span>NIIT AI SEO Agent</span>
          </Link>
          <Button
            variant="ghost"
            size="icon"
            className="text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-foreground md:hidden"
            onClick={() => setMenuOpen(false)}
            aria-label="Close navigation"
          >
            <X />
          </Button>
        </div>
        <nav aria-label="Main" className="flex-1 overflow-y-auto px-2 py-3">
          {NAV_GROUPS.map((group) => (
            <div key={group} className="mb-3">
              <p id={`nav-${group}`} className="px-3 pb-1 text-[0.65rem] font-semibold uppercase tracking-widest text-sidebar-muted/80">
                {group}
              </p>
              <ul className="space-y-0.5" aria-labelledby={`nav-${group}`}>
                {NAV_ITEMS.filter((item) => item.group === group).map((item) => {
                  const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
                  const Icon = item.icon;
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        aria-current={active ? "page" : undefined}
                        onClick={() => setMenuOpen(false)}
                        className={cn(
                          "group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-all hover:bg-sidebar-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-foreground/60",
                          active
                            ? "bg-sidebar-accent font-medium text-white shadow-inner"
                            : "text-sidebar-foreground/80 hover:translate-x-0.5 hover:text-sidebar-foreground",
                        )}
                      >
                        {active ? (
                          <span className="absolute inset-y-1.5 left-0 w-1 rounded-full bg-gradient-to-b from-brand-teal to-brand-violet" aria-hidden />
                        ) : null}
                        <Icon className={cn("size-4 shrink-0 transition-colors", active ? "text-brand-teal" : "group-hover:text-brand-teal")} aria-hidden />
                        <span className="flex-1">{item.label}</span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>
        <p className="shrink-0 border-t border-white/10 px-5 py-3 text-[0.7rem] leading-relaxed text-sidebar-muted">
          Drafts only: nothing is published without a person&apos;s approval.
        </p>
      </aside>
      {menuOpen ? (
        <div className="fixed inset-0 z-30 bg-black/40 md:hidden" onClick={() => setMenuOpen(false)} aria-hidden />
      ) : null}
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar onOpenMenu={() => setMenuOpen(true)} />
        <main id="main" tabIndex={-1} className="flex-1 px-4 py-6 md:px-8">
          <div className="mx-auto max-w-6xl">{children}</div>
        </main>
      </div>
    </div>
  );
}

function TopBar({ onOpenMenu }: { onOpenMenu: () => void }) {
  const { me, signOut } = useSession();
  const { organisations, current, setCurrentId } = useCurrentOrg();
  const router = useRouter();

  return (
    <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b bg-card/95 px-4 backdrop-blur md:px-8">
      <Button variant="ghost" size="icon" className="md:hidden" onClick={onOpenMenu} aria-label="Open navigation">
        <Menu />
      </Button>
      {organisations.length > 0 ? (
        <div className="flex min-w-0 items-center gap-2">
          <label htmlFor="org-switcher" className="sr-only">
            Current organisation
          </label>
          <NativeSelect
            id="org-switcher"
            className="h-8 max-w-64 truncate"
            value={current?.id ?? ""}
            onChange={(e) => setCurrentId(e.target.value)}
          >
            {organisations.map((org) => (
              <option key={org.id} value={org.id}>
                {org.name}
              </option>
            ))}
          </NativeSelect>
          {current?.my_role ? (
            <Badge variant="secondary" className="hidden sm:inline-flex">
              {ROLE_LABELS[current.my_role]}
            </Badge>
          ) : current ? (
            <Badge variant="outline" className="hidden sm:inline-flex">
              Platform admin
            </Badge>
          ) : null}
        </div>
      ) : null}
      <div className="ml-auto flex items-center gap-3">
        {me ? (
          <span className="hidden items-center gap-2 sm:flex">
            <span
              className="flex size-8 items-center justify-center rounded-full bg-gradient-to-br from-brand-violet to-brand-glow text-xs font-semibold text-white"
              aria-hidden
            >
              {initials(me.user.full_name)}
            </span>
            <span className="text-sm text-muted-foreground">{me.user.full_name}</span>
          </span>
        ) : null}
        <Button
          variant="outline"
          size="sm"
          onClick={async () => {
            await signOut();
            router.replace("/login");
          }}
        >
          <LogOut aria-hidden /> Sign out
        </Button>
      </div>
    </header>
  );
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase() || "?";
}
