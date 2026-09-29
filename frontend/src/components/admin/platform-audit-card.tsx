"use client";

import { useState } from "react";

import { ErrorState, LoadingState } from "@/components/app/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { usePlatformAudit } from "@/lib/queries";
import { formatDateTime } from "@/lib/utils";

/** Every audit entry across the platform, including sign-ins. Platform administrators only. */
export function PlatformAuditCard() {
  const [page, setPage] = useState(1);
  const [platformOnly, setPlatformOnly] = useState(true);
  const audit = usePlatformAudit(page, platformOnly, true);
  const data = audit.data;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Platform audit log</CardTitle>
        <CardDescription>
          Visible to platform administrators only. Includes sign-ins, password resets, plan changes and retention runs.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" className="size-4" checked={platformOnly} onChange={(e) => { setPlatformOnly(e.target.checked); setPage(1); }} />
          Only events that belong to no organisation
        </label>
        {audit.isLoading ? (
          <LoadingState rows={4} />
        ) : audit.error ? (
          <ErrorState error={audit.error} onRetry={() => void audit.refetch()} />
        ) : data ? (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>When</TableHead>
                  <TableHead>Action</TableHead>
                  <TableHead>IP address</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((e) => (
                  <TableRow key={e.id}>
                    <TableCell className="whitespace-nowrap">{formatDateTime(e.created_at)}</TableCell>
                    <TableCell className="font-mono text-xs">{e.action}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">{e.ip_address ?? "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <div className="flex items-center justify-end gap-2 text-sm">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
              <span>Page {page} of {Math.max(1, Math.ceil(data.total / data.page_size))}</span>
              <Button variant="outline" size="sm" disabled={page * data.page_size >= data.total} onClick={() => setPage(page + 1)}>Next</Button>
            </div>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
