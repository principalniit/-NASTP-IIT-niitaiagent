import Link from "next/link";

import { SeverityBadge } from "@/components/seo/severity";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { CATEGORY_LABELS, type Issue } from "@/lib/types";
import { pathOf } from "@/lib/utils";

export function affectedLabel(issue: Issue): string {
  if (issue.scope === "site") return "Whole site";
  if (issue.scope === "page" && issue.affected_url) return pathOf(issue.affected_url);
  return `${issue.affected_page_count} pages`;
}

export function IssueTable({ issues, showCategory = true }: { issues: Issue[]; showCategory?: boolean }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-28">Severity</TableHead>
          <TableHead>Issue</TableHead>
          <TableHead className="hidden md:table-cell">Affects</TableHead>
          {showCategory ? <TableHead className="hidden lg:table-cell">Category</TableHead> : null}
          <TableHead className="text-right">Priority</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {issues.map((issue) => (
          <TableRow key={issue.id}>
            <TableCell>
              <SeverityBadge severity={issue.severity} />
            </TableCell>
            <TableCell className="max-w-md">
              <Link href={`/issues/${issue.id}`} className="font-medium text-primary underline-offset-4 hover:underline">
                {issue.title}
              </Link>
              <div className="mt-0.5 flex flex-wrap gap-1 md:hidden">
                <span className="truncate text-xs text-muted-foreground">{affectedLabel(issue)}</span>
              </div>
              {issue.resolution_status !== "open" ? (
                <Badge variant="outline" className="ml-2">
                  {issue.resolution_status}
                </Badge>
              ) : null}
              {issue.recurrence_count > 0 ? (
                <Badge variant="outline" className="ml-2">
                  recurred
                </Badge>
              ) : null}
            </TableCell>
            <TableCell className="hidden max-w-60 truncate text-muted-foreground md:table-cell" title={issue.affected_url ?? undefined}>
              {affectedLabel(issue)}
            </TableCell>
            {showCategory ? (
              <TableCell className="hidden text-muted-foreground lg:table-cell">{CATEGORY_LABELS[issue.category]}</TableCell>
            ) : null}
            <TableCell className="text-right tabular-nums">{issue.priority_score.toFixed(0)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
