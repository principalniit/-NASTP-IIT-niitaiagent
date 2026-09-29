"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Play } from "lucide-react";
import { useRouter } from "next/navigation";
import { useId, useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { api, ApiError } from "@/lib/api";
import { keys } from "@/lib/queries";
import type { CrawlJob } from "@/lib/types";

export function StartCrawlButton({
  projectId,
  organisationId,
  disabled,
  navigate = true,
}: {
  projectId: string;
  organisationId: string;
  disabled?: boolean;
  navigate?: boolean;
}) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const checkboxId = useId();
  const [incremental, setIncremental] = useState(false);
  const start = useMutation({
    mutationFn: () =>
      api<CrawlJob>(`/projects/${projectId}/crawls`, { method: "POST", body: { incremental } }),
    onSuccess: async (job) => {
      await queryClient.invalidateQueries({ queryKey: keys.crawls(organisationId) });
      if (navigate) router.push(`/crawls/${job.id}`);
    },
  });
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-4">
        <Button onClick={() => start.mutate()} disabled={disabled || start.isPending}>
          <Play aria-hidden /> {start.isPending ? "Starting…" : "Start crawl"}
        </Button>
        <div className="flex items-center gap-2">
          <input
            id={checkboxId}
            type="checkbox"
            className="size-4"
            checked={incremental}
            onChange={(e) => setIncremental(e.target.checked)}
          />
          <label htmlFor={checkboxId} className="text-sm">
            Incremental (reuse pages unchanged since the last completed crawl)
          </label>
        </div>
      </div>
      {start.error ? (
        <Alert variant="destructive">
          <AlertDescription>
            {start.error instanceof ApiError ? start.error.message : "The crawl could not be started."}
          </AlertDescription>
        </Alert>
      ) : null}
    </div>
  );
}
