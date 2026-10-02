"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ThumbsDown, ThumbsUp } from "lucide-react";
import { useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError } from "@/lib/api";
import { keys } from "@/lib/queries";
import type { AIAnalysis, FeedbackReason, FeedbackRating, AIFeedback as Feedback } from "@/lib/types";
import { cn } from "@/lib/utils";

export const FEEDBACK_REASONS: Record<FeedbackReason, string> = {
  wrong: "It is wrong",
  off_topic: "It does not answer what was asked",
  vague: "Too vague to act on",
  missed_data: "It missed data the platform has",
  other: "Something else",
};

/**
 * "Was this helpful?" under an AI result. Each person has one verdict, which they can
 * change. Answers marked not helpful are reviewed and become test cases for the AI.
 */
export function AIFeedback({ analysis }: { analysis: AIAnalysis }) {
  const queryClient = useQueryClient();
  const id = useId();
  const saved = analysis.my_feedback;
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState<FeedbackReason>(saved?.reason ?? "off_topic");
  const [comment, setComment] = useState(saved?.comment ?? "");
  const send = useMutation({
    mutationFn: (body: { rating: FeedbackRating; reason?: FeedbackReason; comment?: string }) =>
      api<Feedback>(`/ai-analyses/${analysis.id}/feedback`, { method: "PUT", body }),
    onSuccess: () => {
      setOpen(false);
      void queryClient.invalidateQueries({ queryKey: keys.analysis(analysis.id) });
    },
  });
  const rating = saved?.rating ?? null;

  return (
    <div className="mt-3 space-y-2 text-xs text-muted-foreground" aria-label="Feedback on this result" role="group">
      <div className="flex flex-wrap items-center gap-2">
        <span>Was this helpful?</span>
        <Button
          type="button"
          size="sm"
          variant="outline"
          aria-pressed={rating === "helpful"}
          className={cn("h-7 px-2", rating === "helpful" && "border-primary text-primary")}
          disabled={send.isPending}
          onClick={() => send.mutate({ rating: "helpful" })}
        >
          <ThumbsUp aria-hidden /> Helpful
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          aria-pressed={rating === "not_helpful"}
          aria-expanded={open}
          className={cn("h-7 px-2", rating === "not_helpful" && "border-destructive text-destructive")}
          disabled={send.isPending}
          onClick={() => setOpen((v) => !v)}
        >
          <ThumbsDown aria-hidden /> Not helpful
        </Button>
        {saved && !open ? (
          <span role="status">
            Thanks, your feedback is recorded
            {saved.rating === "not_helpful" && saved.reason ? `: ${FEEDBACK_REASONS[saved.reason].toLowerCase()}` : ""}.
          </span>
        ) : null}
      </div>
      {open ? (
        <form
          className="space-y-2 rounded-lg border bg-muted/30 p-3"
          onSubmit={(e) => {
            e.preventDefault();
            send.mutate({ rating: "not_helpful", reason, comment: comment.trim() || undefined });
          }}
        >
          <label htmlFor={`${id}-reason`} className="block font-medium text-foreground">
            What was wrong with it?
          </label>
          <NativeSelect id={`${id}-reason`} value={reason} onChange={(e) => setReason(e.target.value as FeedbackReason)} className="h-8">
            {(Object.keys(FEEDBACK_REASONS) as FeedbackReason[]).map((r) => (
              <option key={r} value={r}>
                {FEEDBACK_REASONS[r]}
              </option>
            ))}
          </NativeSelect>
          <label htmlFor={`${id}-comment`} className="block">
            Details (optional)
          </label>
          <Textarea id={`${id}-comment`} rows={2} maxLength={500} value={comment} onChange={(e) => setComment(e.target.value)} />
          <div className="flex gap-2">
            <Button type="submit" size="sm" disabled={send.isPending}>
              Send feedback
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
          </div>
        </form>
      ) : null}
      {send.error ? (
        <p className="text-destructive" role="alert">
          {send.error instanceof ApiError ? send.error.message : "Feedback could not be saved."}
        </p>
      ) : null}
    </div>
  );
}
