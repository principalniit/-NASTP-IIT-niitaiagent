"use client";

import { ChevronLeft, ChevronRight, Plus, Search } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { NoOrganisation } from "@/components/app/no-organisation";
import { PageHeader } from "@/components/app/page-header";
import { EmptyState, ErrorState, LoadingState } from "@/components/app/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useCurrentOrg } from "@/lib/current-org";
import { useProjects, type ProjectQuery } from "@/lib/queries";
import { formatDateTime } from "@/lib/utils";

const SORTS: Record<string, Pick<ProjectQuery, "sort" | "order">> = {
  "name-asc": { sort: "name", order: "asc" },
  "created_at-desc": { sort: "created_at", order: "desc" },
  "domain-asc": { sort: "domain", order: "asc" },
};

export function ProjectsView() {
  const { current, can, isLoading: orgLoading } = useCurrentOrg();
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [sortKey, setSortKey] = useState("name-asc");
  const [page, setPage] = useState(1);

  useEffect(() => {
    const t = setTimeout(() => {
      setQ(search);
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const projects = useProjects(current?.id ?? null, { q, page, ...SORTS[sortKey] });

  if (orgLoading) return <LoadingState />;
  if (!current) return <NoOrganisation />;

  const data = projects.data;
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const canCreate = can("projects:create");

  return (
    <>
      <PageHeader
        title="Projects"
        description="Each project is one website analysed for this organisation."
        actions={
          canCreate ? (
            <Button asChild>
              <Link href="/projects/new">
                <Plus aria-hidden /> New project
              </Link>
            </Button>
          ) : null
        }
      />
      <Card>
        <CardContent className="pt-5">
          <div className="mb-4 flex flex-col gap-3 sm:flex-row">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-2.5 size-4 text-muted-foreground" aria-hidden />
              <label htmlFor="project-search" className="sr-only">
                Search projects
              </label>
              <Input
                id="project-search"
                placeholder="Search by name or domain"
                className="pl-9"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <label htmlFor="project-sort" className="sr-only">
              Sort projects
            </label>
            <NativeSelect
              id="project-sort"
              className="sm:w-48"
              value={sortKey}
              onChange={(e) => {
                setSortKey(e.target.value);
                setPage(1);
              }}
            >
              <option value="name-asc">Name A–Z</option>
              <option value="created_at-desc">Newest first</option>
              <option value="domain-asc">Domain A–Z</option>
            </NativeSelect>
          </div>

          {projects.isLoading ? (
            <LoadingState />
          ) : projects.error ? (
            <ErrorState error={projects.error} onRetry={() => void projects.refetch()} />
          ) : !data || data.items.length === 0 ? (
            <EmptyState
              title={q ? "No projects match your search" : "No projects yet"}
              description={
                q
                  ? "Try a different name or domain."
                  : canCreate
                    ? "Add the website you want to analyse. Crawling becomes available in Phase 2."
                    : "An administrator has not added any projects yet."
              }
              action={
                !q && canCreate ? (
                  <Button asChild size="sm">
                    <Link href="/projects/new">New project</Link>
                  </Button>
                ) : null
              }
            />
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Domain</TableHead>
                    <TableHead className="hidden md:table-cell">Created</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.items.map((project) => (
                    <TableRow key={project.id}>
                      <TableCell>
                        <Link
                          href={`/projects/${project.id}`}
                          className="font-medium text-primary underline-offset-4 hover:underline"
                        >
                          {project.name}
                        </Link>
                      </TableCell>
                      <TableCell className="text-muted-foreground">{project.domain}</TableCell>
                      <TableCell className="hidden text-muted-foreground md:table-cell">
                        {formatDateTime(project.created_at, current.timezone)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <nav aria-label="Pagination" className="mt-4 flex items-center justify-between text-sm">
                <span className="text-muted-foreground">
                  {data.total} project{data.total === 1 ? "" : "s"} · page {page} of {totalPages}
                </span>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                    <ChevronLeft aria-hidden /> Previous
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={page >= totalPages}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    Next <ChevronRight aria-hidden />
                  </Button>
                </div>
              </nav>
            </>
          )}
        </CardContent>
      </Card>
    </>
  );
}
