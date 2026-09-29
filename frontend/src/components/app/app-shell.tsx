"use client";

import { LogOut, Menu, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { LoadingState } from "@/components/app/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import { CurrentOrgProvider, useCurrentOrg } from "@/lib/current-org";
import { NAV_ITEMS } from "@/lib/navigation";
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
          "fixed inset-y-0 left-0 z-40 w-64 -translate-x-full bg-sidebar text-sidebar-foreground transition-transform md:static md:translate-x-0",
          menuOpen && "translate-x-0",
        )}
      >
        <div className="flex h-14 items-center justify-between border-b border-white/10 px-4">
          <Link href="/overview" className="font-semibold tracking-tight">
            NIIT AI SEO Agent
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
        <nav aria-label="Main" className="overflow-y-auto p-2" style={{ maxHeight: "calc(100vh - 3.5rem)" }}>
          <ul className="space-y-0.5">
            {NAV_ITEMS.map((item) => {
              const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
              const Icon = item.icon;
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    onClick={() => setMenuOpen(false)}
                    className={cn(
                      "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors hover:bg-sidebar-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-foreground/60",
                      active ? "bg-sidebar-accent font-medium" : "text-sidebar-foreground/85",
                    )}
                  >
                    <Icon className="size-4 shrink-0" aria-hidden />
                    <span className="flex-1">{item.label}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
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
        <span className="hidden text-sm text-muted-foreground sm:inline">{me?.user.full_name}</span>
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
