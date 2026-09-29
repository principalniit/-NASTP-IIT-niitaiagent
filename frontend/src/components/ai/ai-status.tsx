"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Bot } from "lucide-react";
import Link from "next/link";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { api } from "@/lib/api";
import { useCurrentOrg } from "@/lib/current-org";
import { keys, useAIStatus } from "@/lib/queries";
import type { AIAnalysisSummary, AIRequest } from "@/lib/types";

/** Whether the AI assistant can take requests, with the reason when it cannot. */
export function useAIReady() {
  const { current } = useCurrentOrg();
  const status = useAIStatus(current?.id ?? null);
  return { status: status.data, isLoading: status.isLoading, ready: !!status.data?.enabled };
}

/** Explains why AI features are unavailable. Renders nothing when AI is ready. */
export function AIStatusNotice({ compact = false }: { compact?: boolean }) {
  const { status } = useAIReady();
  const { can } = useCurrentOrg();
  if (!status || status.status === "available") return null;
  const disabled = status.status === "disabled";
  const detail = disabled
    ? `${status.detail ?? "AI is not enabled."} Crawling, analysis, scores and issues work without it.`
    : `The AI service is not responding (${status.detail ?? "unknown reason"}). Requests will fail until it is back.`;
  if (compact) return <p className="text-sm text-muted-foreground">{detail}</p>;
  return (
    <Alert className="mb-6">
      <Bot aria-hidden />
      <AlertTitle>{disabled ? "The AI assistant is off" : "The AI assistant is unavailable"}</AlertTitle>
      <AlertDescription>
        <p>{detail}</p>
        {disabled && can("org:update") ? (
          <p>
            An administrator can turn it on in{" "}
            <Link href="/settings" className="font-medium text-primary underline-offset-4 hover:underline">
              organisation settings
            </Link>{" "}
            once a local Ollama model is installed.
          </p>
        ) : null}
      </AlertDescription>
    </Alert>
  );
}

export function useRequestAnalysis(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: AIRequest) =>
      api<AIAnalysisSummary>(`/projects/${projectId}/ai/analyses`, { method: "POST", body }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: keys.analyses(projectId) }),
  });
}
