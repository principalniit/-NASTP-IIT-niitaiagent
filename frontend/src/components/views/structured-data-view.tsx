"use client";

import Link from "next/link";
import { useState } from "react";

import { PageHeader } from "@/components/app/page-header";
import { ErrorState, LoadingState } from "@/components/app/states";
import { AnalysisGate, type AnalysedContext } from "@/components/seo/analysis-gate";
import { IssueTable } from "@/components/seo/issue-table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useIssues, useSchemaFindings } from "@/lib/queries";
import { pathOf } from "@/lib/utils";

export function StructuredDataView() {
  return (
    <AnalysisGate
      header={(picker) => (
        <PageHeader
          title="Structured Data"
          description="JSON-LD and microdata found on crawled pages. Errors and optional enhancements are kept apart."
          actions={picker}
        />
      )}
    >
      {(ctx) => <SchemaBody {...ctx} />}
    </AnalysisGate>
  );
}

function SchemaBody({ project, crawl }: AnalysedContext) {
  const [page, setPage] = useState(1);
  const [invalidOnly, setInvalidOnly] = useState(false);
  const findings = useSchemaFindings(crawl.id, page, invalidOnly);
  const issues = useIssues(project.id, { status: "open", category: "structured_data", page_size: 50 });
  const totalPages = findings.data ? Math.max(1, Math.ceil(findings.data.total / findings.data.page_size)) : 1;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Structured data issues and opportunities</CardTitle>
          <CardDescription>
            Checks cover common schema.org types and the properties search engines document as required or
            recommended. Only add values that are verified.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {issues.isLoading ? (
            <LoadingState />
          ) : issues.data?.items.length ? (
            <IssueTable issues={issues.data.items} showCategory={false} />
          ) : (
            <p className="text-sm text-muted-foreground">No open structured data issues.</p>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <CardTitle>Markup found</CardTitle>
              <CardDescription>One row per JSON-LD block or microdata set.</CardDescription>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="size-4"
                checked={invalidOnly}
                onChange={(e) => {
                  setInvalidOnly(e.target.checked);
                  setPage(1);
                }}
              />
              Only blocks with errors
            </label>
          </div>
        </CardHeader>
        <CardContent>
          {findings.isLoading ? (
            <LoadingState />
          ) : findings.error ? (
            <ErrorState error={findings.error} onRetry={() => void findings.refetch()} />
          ) : !findings.data?.items.length ? (
            <p className="text-sm text-muted-foreground">
              {invalidOnly ? "No blocks with errors." : "No structured data was found on the crawled pages."}
            </p>
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Page</TableHead>
                    <TableHead>Types</TableHead>
                    <TableHead>Result</TableHead>
                    <TableHead className="hidden md:table-cell">Details</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {findings.data.items.map((f) => (
                    <TableRow key={f.id}>
                      <TableCell className="max-w-56 truncate">
                        <Link href={`/crawls/${crawl.id}/pages/${f.page_id}`} className="text-primary underline-offset-4 hover:underline">
                          {pathOf(f.page_url)}
                        </Link>
                        <span className="block text-xs text-muted-foreground">{f.format === "json_ld" ? "JSON-LD" : "Microdata"}</span>
                      </TableCell>
                      <TableCell>{f.schema_types.join(", ") || <span className="text-muted-foreground">none</span>}</TableCell>
                      <TableCell>
                        <Badge variant={f.is_valid ? "success" : "destructive"}>{f.is_valid ? "No errors" : `${f.errors.length} error(s)`}</Badge>
                      </TableCell>
                      <TableCell className="hidden text-sm md:table-cell">
                        {[...f.errors, ...f.warnings].slice(0, 4).map((m) => (
                          <span key={m} className="block">{m}</span>
                        ))}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              {totalPages > 1 ? (
                <nav aria-label="Markup pagination" className="mt-4 flex justify-end gap-2">
                  <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((n) => n - 1)}>Previous</Button>
                  <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage((n) => n + 1)}>Next</Button>
                </nav>
              ) : null}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
