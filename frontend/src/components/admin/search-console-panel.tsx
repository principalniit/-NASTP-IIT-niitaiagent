"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Copy, RefreshCw, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api, ApiError } from "@/lib/api";
import { useCurrentOrg } from "@/lib/current-org";
import { keys, useSearchSyncs } from "@/lib/queries";
import type { Integration, SearchSync } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

const STATUS: Record<SearchSync["status"], string> = {
  queued: "Waiting for the worker",
  running: "Importing",
  succeeded: "Imported",
  failed: "Failed",
};

/**
 * Setup and syncing for a Google Search Console integration: the service account to add
 * to the property, a connection test, and imports. Read-only access to Google.
 */
export function SearchConsolePanel({ integration }: { integration: Integration }) {
  const { current } = useCurrentOrg();
  const queryClient = useQueryClient();
  const syncs = useSearchSyncs(integration.id, integration.secret_set);
  const email = typeof integration.config.service_account_email === "string" ? integration.config.service_account_email : null;
  const [copied, setCopied] = useState(false);
  const test = useMutation({
    mutationFn: () =>
      api<{ permission_level: string; service_account_email: string }>(`/integrations/${integration.id}/search-console/test`, { method: "POST" }),
  });
  const sync = useMutation({
    mutationFn: () => api<SearchSync>(`/integrations/${integration.id}/search-console/syncs`, { method: "POST" }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: keys.searchSyncs(integration.id) }),
  });
  const latest = syncs.data?.[0];

  return (
    <div className="space-y-3 rounded-lg border bg-muted/30 p-4" aria-label="Search Console connection" role="group">
      <h3 className="flex items-center gap-2 text-sm font-semibold">
        <ShieldCheck className="size-4 text-primary" aria-hidden /> Read-only connection to Google Search Console
      </h3>
      {!integration.secret_set ? (
        <ol className="list-decimal space-y-1 pl-5 text-sm text-muted-foreground">
          <li>In your Google Cloud project (free), enable the Search Console API and create a service account.</li>
          <li>Create a JSON key for it and save the file below as the credential.</li>
          <li>In Search Console, open the property, then Settings, Users and permissions, and add the service account&apos;s email with Restricted access.</li>
        </ol>
      ) : (
        <>
          {email ? (
            <p className="text-sm">
              Add <span className="break-all font-mono text-xs">{email}</span> as a user of the property in Search Console
              (Restricted is enough).{" "}
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="h-7 px-2"
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(email);
                    setCopied(true);
                  } catch {
                    setCopied(false);
                  }
                }}
              >
                <Copy aria-hidden /> {copied ? "Copied" : "Copy email"}
              </Button>
            </p>
          ) : null}
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" disabled={test.isPending} onClick={() => test.mutate()}>
              {test.isPending ? "Testing…" : "Test connection"}
            </Button>
            <Button size="sm" disabled={sync.isPending || latest?.status === "queued" || latest?.status === "running"} onClick={() => sync.mutate()}>
              <RefreshCw aria-hidden /> Import now
            </Button>
          </div>
          {test.data ? (
            <p className="flex items-center gap-2 text-sm text-success" role="status">
              <CheckCircle2 className="size-4" aria-hidden /> Connected: the service account can read this property ({test.data.permission_level}).
            </p>
          ) : null}
          {latest ? (
            <p className="text-sm text-muted-foreground" role="status">
              Latest import: <Badge variant={latest.status === "failed" ? "destructive" : "secondary"}>{STATUS[latest.status]}</Badge>{" "}
              {latest.status === "succeeded" && latest.start_date && latest.end_date
                ? `${latest.start_date} to ${latest.end_date}, ${latest.page_day_rows.toLocaleString("en")} page-days and ${latest.query_rows.toLocaleString("en")} query rows`
                : ""}
              {latest.finished_at ? `, ${formatDateTime(latest.finished_at, current?.timezone)}` : ""}
              {latest.error ? <span className="mt-1 block text-destructive">{latest.error}</span> : null}
            </p>
          ) : (
            <p className="text-sm text-muted-foreground">Nothing imported yet. When the integration is turned on, it imports once a day.</p>
          )}
        </>
      )}
      {test.error || sync.error ? (
        <Alert variant="destructive">
          <AlertDescription>
            {(test.error ?? sync.error) instanceof ApiError ? (test.error ?? sync.error)!.message : "The request failed."}
          </AlertDescription>
        </Alert>
      ) : null}
    </div>
  );
}
