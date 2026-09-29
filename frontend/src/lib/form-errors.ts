import type { FieldValues, Path, UseFormSetError } from "react-hook-form";

import { ApiError } from "@/lib/api";

/**
 * Attach API validation errors to form fields using `fieldMap` (API location such as
 * "root_url" or "settings.crawl.max_pages" to form field name). Returns a message for the
 * form-level alert covering anything that could not be attached, or null.
 */
export function applyApiErrors<T extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<T>,
  fieldMap: Record<string, Path<T>>,
): string | null {
  if (!(error instanceof ApiError)) return "The request failed. Please try again.";
  const details = error.fieldErrors();
  if (details.length === 0) return error.message;
  const unmatched: string[] = [];
  for (const detail of details) {
    const loc = (detail.loc ?? []).filter((part) => part !== "body").join(".");
    const message = (detail.msg ?? "Invalid value").replace(/^Value error, /, "");
    const field = fieldMap[loc];
    if (field) setError(field, { type: "server", message });
    else unmatched.push(loc ? `${loc}: ${message}` : message);
  }
  return unmatched.length ? unmatched.join("; ") : null;
}
