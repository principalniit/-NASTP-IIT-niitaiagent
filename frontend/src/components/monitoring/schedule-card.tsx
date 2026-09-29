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
import { keys, useSchedule } from "@/lib/queries";
import type { Project, Schedule, ScheduleFrequency } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

const FREQUENCIES: Record<ScheduleFrequency, string> = { daily: "Every day", weekly: "Every week", monthly: "Every month" };

export function ScheduleCard({ project, canEdit }: { project: Project; canEdit: boolean }) {
  const schedule = useSchedule(project.id);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Scheduled crawls</CardTitle>
        <CardDescription>Crawl this project automatically. Off by default.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {schedule.data ? <ScheduleForm project={project} schedule={schedule.data} canEdit={canEdit} /> : <LoadingState rows={2} />}
      </CardContent>
    </Card>
  );
}

function ScheduleForm({ project, schedule: s, canEdit }: { project: Project; schedule: Schedule; canEdit: boolean }) {
  const queryClient = useQueryClient();
  const enabledId = useId();
  const frequencyId = useId();
  const hourId = useId();
  const [draft, setDraft] = useState({ enabled: s.enabled, frequency: s.frequency, hour: s.hour });
  const save = useMutation({
    mutationFn: (body: Pick<Schedule, "enabled" | "frequency" | "hour">) =>
      api<Schedule>(`/projects/${project.id}/schedule`, { method: "PUT", body }),
    onSuccess: (saved) => queryClient.setQueryData(keys.schedule(project.id), saved),
  });
  return (
    <>
      {!s.platform_enabled ? (
        <Alert>
          <AlertDescription>
            Scheduling is switched off on this server, so nothing runs automatically even if a schedule is saved. The
            operator can enable it with <code>SCHEDULER_ENABLED=true</code>.
          </AlertDescription>
        </Alert>
      ) : null}
      <div className="flex items-center gap-2">
        <input
          id={enabledId}
          type="checkbox"
          className="size-4"
          checked={draft.enabled}
          disabled={!canEdit}
          onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })}
        />
        <Label htmlFor={enabledId} className="font-normal">Crawl on a schedule</Label>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label htmlFor={frequencyId}>How often</Label>
          <NativeSelect id={frequencyId} value={draft.frequency} disabled={!canEdit} onChange={(e) => setDraft({ ...draft, frequency: e.target.value as ScheduleFrequency })}>
            {Object.entries(FREQUENCIES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </NativeSelect>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={hourId}>At ({s.timezone})</Label>
          <NativeSelect id={hourId} value={draft.hour} disabled={!canEdit} onChange={(e) => setDraft({ ...draft, hour: Number(e.target.value) })}>
            {Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{String(h).padStart(2, "0")}:00</option>)}
          </NativeSelect>
        </div>
      </div>
      <p className="text-xs text-muted-foreground">
        {s.enabled && s.next_run_at ? `Next crawl: ${formatDateTime(s.next_run_at, s.timezone)}.` : "Not scheduled."}
        {s.last_run_at ? ` Last scheduled crawl: ${formatDateTime(s.last_run_at, s.timezone)}.` : ""} Choose a quiet hour
        for the website. A run is skipped if a crawl is already in progress.
      </p>
      {save.error ? (
        <Alert variant="destructive"><AlertDescription>{save.error instanceof ApiError ? save.error.message : "Could not save."}</AlertDescription></Alert>
      ) : null}
      {canEdit ? <Button size="sm" onClick={() => save.mutate(draft)} disabled={save.isPending}>Save schedule</Button> : null}
      {save.isSuccess ? <p role="status" className="text-sm text-success">Schedule saved</p> : null}
    </>
  );
}
