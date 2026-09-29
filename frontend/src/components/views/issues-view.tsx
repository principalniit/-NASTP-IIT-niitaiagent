"use client";

import { ChevronLeft, ChevronRight, Search } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { NoOrganisation } from "@/components/app/no-organisation";
import { PageHeader } from "@/components/app/page-header";
import { EmptyState, ErrorState, LoadingState } from "@/components/app/states";
import { IssueTable } from "@/components/seo/issue-table";
import { ProjectPicker, useProjectChoice } from "@/components/seo/project-picker";
import { SEVERITY_STYLE } from "@/components/seo/severity";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { useCurrentOrg } from "@/lib/current-org";
import { useIssues } from "@/lib/queries";
import { CATEGORY_LABELS, SEVERITIES, type IssueCategory } from "@/lib/types";

export function IssuesView() {
  const { current, isLoading } = useCurrentOrg();
  const params = useSearchParams();
  const choice = useProjectChoice(current?.id ?? null);
  const [status, setStatus] = useState(params.get("status") ?? "open");
  const [severity, setSeverity] = useState(params.get("severity") ?? "");
  const [category, setCategory] = useState(params.get("category") ?? "");
  const [ruleId, setRuleId] = useState(params.get("rule_id") ?? "");
  const [sort, setSort] = useState("priority");
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);

  useEffect(() => {
    const t = setTimeout(() => {
      setQ(search);
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const issues = useIssues(choice.project?.id ?? null, {
    status: status === "all" ? undefined : status,
    all_statuses: status === "all" ? "true" : undefined,
    severity: severity || undefined,
    category: category || undefined,
    rule_id: ruleId || undefined,
    q: q || undefined,
    sort,
    order: "desc",
    page,
  });

  if (isLoading || choice.isLoading) return <LoadingState />;
  if (!current) return <NoOrganisation />;
  const data = issues.data;
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const reset = (fn: () => void) => {
    fn();
    setPage(1);
  };

  return (
    <>
      <PageHeader
        title="Issues"
        description="Every finding has evidence and a recommendation. Issues resolve only when a later crawl confirms the fix."
        actions={<ProjectPicker projects={choice.projects} project={choice.project} onChange={(id) => reset(() => choice.choose(id))} />}
      />
      {!choice.project ? (
        <EmptyState title="No projects yet" description="Add and crawl a project to see issues." />
      ) : (
        <Card>
          <CardContent className="space-y-4 pt-5">
            <div className="grid gap-3 md:grid-cols-5">
              <div className="relative md:col-span-2">
                <Search className="absolute left-3 top-2.5 size-4 text-muted-foreground" aria-hidden />
                <label htmlFor="issue-search" className="sr-only">
                  Search issues by title or URL
                </label>
                <Input id="issue-search" className="pl-9" placeholder="Search title or URL" value={search} onChange={(e) => setSearch(e.target.value)} />
              </div>
              <div>
                <label htmlFor="issue-status" className="sr-only">Status</label>
                <NativeSelect id="issue-status" value={status} onChange={(e) => reset(() => setStatus(e.target.value))}>
                  <option value="open">Open</option>
                  <option value="ignored">Ignored</option>
                  <option value="resolved">Resolved</option>
                  <option value="all">All statuses</option>
                </NativeSelect>
              </div>
              <div>
                <label htmlFor="issue-severity" className="sr-only">Severity</label>
                <NativeSelect id="issue-severity" value={severity} onChange={(e) => reset(() => setSeverity(e.target.value))}>
                  <option value="">All severities</option>
                  {SEVERITIES.map((s) => (
                    <option key={s} value={s}>{SEVERITY_STYLE[s].label}</option>
                  ))}
                </NativeSelect>
              </div>
              <div>
                <label htmlFor="issue-category" className="sr-only">Category</label>
                <NativeSelect id="issue-category" value={category} onChange={(e) => reset(() => setCategory(e.target.value))}>
                  <option value="">All categories</option>
                  {(Object.keys(CATEGORY_LABELS) as IssueCategory[]).map((c) => (
                    <option key={c} value={c}>{CATEGORY_LABELS[c]}</option>
                  ))}
                </NativeSelect>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <label htmlFor="issue-sort" className="text-muted-foreground">Sort by</label>
              <NativeSelect id="issue-sort" className="w-48" value={sort} onChange={(e) => reset(() => setSort(e.target.value))}>
                <option value="priority">Priority</option>
                <option value="severity">Severity</option>
                <option value="affected">Pages affected</option>
                <option value="last_detected">Most recently detected</option>
              </NativeSelect>
              {ruleId ? (
                <Button variant="outline" size="sm" onClick={() => reset(() => setRuleId(""))}>
                  Rule: <span className="font-mono">{ruleId}</span> ✕
                </Button>
              ) : null}
            </div>
            {issues.isLoading ? (
              <LoadingState />
            ) : issues.error ? (
              <ErrorState error={issues.error} onRetry={() => void issues.refetch()} />
            ) : !data?.items.length ? (
              <EmptyState
                title="No issues match"
                description={status === "open" && !severity && !category && !q && !ruleId
                  ? "No open issues. Either the project has not been analysed yet, or every issue is resolved or ignored."
                  : "Try different filters."}
              />
            ) : (
              <>
                <IssueTable issues={data.items} />
                <nav aria-label="Issues pagination" className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">
                    {data.total} issue{data.total === 1 ? "" : "s"} · page {page} of {totalPages}
                  </span>
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((n) => n - 1)}>
                      <ChevronLeft aria-hidden /> Previous
                    </Button>
                    <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage((n) => n + 1)}>
                      Next <ChevronRight aria-hidden />
                    </Button>
                  </div>
                </nav>
              </>
            )}
          </CardContent>
        </Card>
      )}
    </>
  );
}
