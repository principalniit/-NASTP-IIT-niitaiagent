"use client";

import { createContext, useContext, useMemo, useState } from "react";

import { useOrganisations } from "@/lib/queries";
import type { Organisation } from "@/lib/types";

const STORAGE_KEY = "niit-seo.current-organisation";

interface CurrentOrgValue {
  organisations: Organisation[];
  current: Organisation | null;
  setCurrentId: (id: string) => void;
  can: (permission: string) => boolean;
  isLoading: boolean;
  error: unknown;
  refetch: () => void;
}

const CurrentOrgContext = createContext<CurrentOrgValue | null>(null);

function readStored(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function CurrentOrgProvider({ children }: { children: React.ReactNode }) {
  const query = useOrganisations();
  // Rendered only on the client after sign-in, so reading storage during init is safe.
  const [selectedId, setSelectedId] = useState<string | null>(readStored);

  const organisations = useMemo(() => query.data?.items ?? [], [query.data]);
  const current =
    organisations.find((o) => o.id === selectedId) ??
    organisations.find((o) => o.my_role !== null) ??
    organisations[0] ??
    null;

  const value = useMemo<CurrentOrgValue>(
    () => ({
      organisations,
      current,
      setCurrentId: (id: string) => {
        setSelectedId(id);
        try {
          window.localStorage.setItem(STORAGE_KEY, id);
        } catch {
          // Storage may be unavailable (private mode); selection still works for this tab.
        }
      },
      can: (permission: string) => !!current?.my_permissions.includes(permission),
      isLoading: query.isLoading,
      error: query.error,
      refetch: () => void query.refetch(),
    }),
    [organisations, current, query],
  );
  return <CurrentOrgContext.Provider value={value}>{children}</CurrentOrgContext.Provider>;
}

export function useCurrentOrg(): CurrentOrgValue {
  const value = useContext(CurrentOrgContext);
  if (!value) throw new Error("useCurrentOrg must be used inside CurrentOrgProvider");
  return value;
}
