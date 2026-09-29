"use client";

import { ArrowUpRight, ChevronLeft, ChevronRight, LayoutGrid, Plus, Rows3, Search } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { NoOrganisation } from "@/components/app/no-organisation";
import { PageHeader } from "@/components/app/page-header";
import { ScoreRing } from "@/components/app/score-ring";
import { EmptyState, ErrorState, LoadingState } from "@/components/app/states";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useCurrentOrg } from "@/lib/current-org";
import { useLatestAnalysedCrawl, useProjects, useScore, type ProjectQuery } from "@/lib/queries";
import type { Project } from "@/lib/types";
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
  const [layout, setLayout] = useState("tiles");

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
                    ? "Add the website you want to analyse, then start a crawl."
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
            <Tabs value={layout} onValueChange={setLayout}>
              <TabsList label="Project layout">
                <TabsTrigger value="tiles">
                  <LayoutGrid aria-hidden /> Tiles
                </TabsTrigger>
                <TabsTrigger value="table">
                  <Rows3 aria-hidden /> Table
                </TabsTrigger>
              </TabsList>
              <TabsContent value="tiles">
                <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {data.items.map((project, i) => (
                    <li key={project.id} className="animate-fade-up" style={{ animationDelay: `${i * 50}ms` }}>
                      <ProjectTile project={project} orgId={current.id} />
                    </li>
                  ))}
                </ul>
              </TabsContent>
              <TabsContent value="table">
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
              </TabsContent>
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
            </Tabs>
          )}
        </CardContent>
      </Card>
    </>
  );
}

/** A stable hue per domain within the brand's teal-to-violet range. */
function hue(text: string): number {
  let h = 0;
  for (let i = 0; i < text.length; i++) h = (h * 31 + text.charCodeAt(i)) % 997;
  return 190 + (h % 110);
}

function ProjectTile({ project, orgId }: { project: Project; orgId: string }) {
  const latest = useLatestAnalysedCrawl(orgId, project.id);
  const score = useScore(latest.crawl?.id ?? null);
  const h = hue(project.domain);
  const overall = score.data?.overall ?? null;
  return (
    <Link
      href={`/projects/${project.id}`}
      className="group block h-full overflow-hidden rounded-xl border bg-card shadow-sm transition-all duration-200 hover:-translate-y-1 hover:border-primary/40 hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <span className="block px-4 pt-4 font-medium">{project.name}</span>
      <span
        className="mx-4 mt-3 flex h-24 items-center justify-between overflow-hidden rounded-lg px-4 text-white"
        style={{ backgroundImage: `linear-gradient(135deg, oklch(0.5 0.14 ${h}), oklch(0.3 0.1 ${h + 35}))` }}
        aria-hidden
      >
        <span className="text-4xl font-semibold uppercase tracking-tight opacity-90 transition-transform duration-300 group-hover:scale-110">
          {project.domain.replace(/^www\./, "").slice(0, 2)}
        </span>
        <ArrowUpRight className="size-5 opacity-70 transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
      </span>
      <span className="flex items-center justify-between gap-3 p-4">
        <span className="min-w-0">
          <span className="block truncate text-sm text-muted-foreground">{project.domain}</span>
          <span className="block text-xs text-muted-foreground">
            {latest.isLoading ? "Checking…" : latest.crawl ? "Latest analysed crawl" : "Not analysed yet"}
          </span>
        </span>
        {latest.crawl ? <ScoreRing value={overall} label={`${project.name} health score`} size={56} compact /> : null}
      </span>
    </Link>
  );
}
