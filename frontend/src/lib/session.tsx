"use client";

import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import {
  api,
  login as apiLogin,
  logout as apiLogout,
  refreshSession,
  setSessionExpiredHandler,
} from "@/lib/api";
import type { Me } from "@/lib/types";

type Status = "loading" | "authenticated" | "anonymous";

interface SessionValue {
  status: Status;
  me: Me | null;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  reload: () => Promise<void>;
}

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<Status>("loading");
  const [me, setMe] = useState<Me | null>(null);

  const reload = useCallback(async () => {
    try {
      setMe(await api<Me>("/auth/me"));
      setStatus("authenticated");
    } catch {
      setMe(null);
      setStatus("anonymous");
    }
  }, []);

  useEffect(() => {
    setSessionExpiredHandler(() => {
      setMe(null);
      setStatus("anonymous");
      queryClient.clear();
    });
    let cancelled = false;
    void (async () => {
      const ok = await refreshSession();
      if (cancelled) return;
      if (ok) await reload();
      else setStatus("anonymous");
    })();
    return () => {
      cancelled = true;
      setSessionExpiredHandler(null);
    };
  }, [queryClient, reload]);

  const signIn = useCallback(
    async (email: string, password: string) => {
      await apiLogin(email, password);
      await reload();
    },
    [reload],
  );

  const signOut = useCallback(async () => {
    await apiLogout();
    queryClient.clear();
    setMe(null);
    setStatus("anonymous");
  }, [queryClient]);

  const value = useMemo(
    () => ({ status, me, signIn, signOut, reload }),
    [status, me, signIn, signOut, reload],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession must be used inside SessionProvider");
  return value;
}
