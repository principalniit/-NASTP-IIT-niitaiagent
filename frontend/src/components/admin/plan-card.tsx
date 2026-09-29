"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";

import { LoadingState } from "@/components/app/states";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { api, ApiError } from "@/lib/api";
import { usePlans, useUsage } from "@/lib/queries";
import { useSession } from "@/lib/session";
import type { Organisation, Usage, UsageResource } from "@/lib/types";

const LABELS: Record<UsageResource, string> = {
  projects: "Projects",
  members: "Members",
  crawls_per_month: "Crawls this month",
  ai_tasks_per_day: "AI tasks today",
  reports_per_month: "Reports this month",
};

/** Used against the plan limit, in one hue, with the numbers printed. */
function UsageMeter({ label, used, limit }: { label: string; used: number; limit: number | null }) {
  const share = limit ? Math.min(1, used / limit) : 0;
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-2 text-sm">
        <span className="font-medium">{label}</span>
        <span className="tabular-nums text-muted-foreground">
          {used} {limit === null ? "· no limit" : `of ${limit}`}
          {limit !== null && used >= limit ? <span className="ml-2 font-medium text-foreground">Limit reached</span> : null}
        </span>
      </div>
      {limit !== null ? (
        <div
          role="meter"
          aria-label={label}
          aria-valuemin={0}
          aria-valuemax={limit}
          aria-valuenow={used}
          aria-valuetext={`${used} of ${limit}`}
          className="h-2 w-full overflow-hidden rounded-full bg-primary/15"
        >
          <div className="h-full rounded-full bg-primary" style={{ width: `${share * 100}%` }} />
        </div>
      ) : null}
    </div>
  );
}

function AssignPlan({ org, usage }: { org: Organisation; usage: Usage }) {
  const plans = usePlans(true);
  const queryClient = useQueryClient();
  const id = useId();
  const [key, setKey] = useState(usage.plan.key);
  const assign = useMutation({
    mutationFn: () => api<Usage>(`/organisations/${org.id}/plan`, { method: "PUT", body: { plan_key: key } }),
    onSuccess: (updated) => queryClient.setQueryData(["organisations", org.id, "usage"], updated),
  });
  if (!plans.data?.length) return null;
  return (
    <div className="flex flex-wrap items-end gap-3 border-t pt-4">
      <div className="space-y-1.5">
        <Label htmlFor={id}>Plan (platform administrators only)</Label>
        <NativeSelect id={id} className="w-56" value={key} onChange={(e) => setKey(e.target.value)}>
          {plans.data.map((p) => (
            <option key={p.key} value={p.key}>{p.name}{p.is_default ? " (default)" : ""}</option>
          ))}
        </NativeSelect>
      </div>
      <Button variant="outline" onClick={() => assign.mutate()} disabled={assign.isPending || key === usage.plan.key}>
        Change plan
      </Button>
      {assign.error ? (
        <Alert variant="destructive"><AlertDescription>{assign.error instanceof ApiError ? assign.error.message : "Could not change the plan."}</AlertDescription></Alert>
      ) : null}
    </div>
  );
}

export function PlanCard({ org }: { org: Organisation }) {
  const usage = useUsage(org.id);
  const { me } = useSession();
  const u = usage.data;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Plan and usage</CardTitle>
        <CardDescription>
          {u ? `${u.plan.name} plan${u.plan_assigned ? "" : " (default)"}. ${u.plan.description ?? ""}` : "Limits for this organisation."}
          {" "}Plans set limits only; there is no billing.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {!u ? (
          <LoadingState rows={3} />
        ) : (
          <>
            <div className="grid gap-4 sm:grid-cols-2">
              {(Object.keys(LABELS) as UsageResource[]).map((r) => (
                <UsageMeter key={r} label={LABELS[r]} used={u.usage[r].used} limit={u.usage[r].limit} />
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              Pages per crawl: {u.max_pages_per_crawl ?? "no plan limit (organisation crawl caps apply)"}. Monthly counts
              reset on the 1st and daily counts at midnight, both in UTC.
            </p>
            {me?.user.is_platform_admin ? <AssignPlan key={u.plan.key} org={org} usage={u} /> : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}
