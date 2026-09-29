"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import {
  ACTIVE_CRAWL_STATUSES,
  type BrokenLink,
  type CrawlJob,
  type CrawlPageDetail,
  type CrawlPageRow,
  type CrawlSummary,
} from "@/lib/types";
import type {
  AuditLogEntry,
  Health,
  Member,
  Organisation,
  Page,
  Project,
  ProjectSettings,
} from "@/lib/types";

export const keys = {
  health: ["health"] as const,
  organisations: ["organisations"] as const,
  organisation: (id: string) => ["organisations", id] as const,
  members: (orgId: string) => ["organisations", orgId, "members"] as const,
  audit: (orgId: string, page: number) => ["organisations", orgId, "audit", page] as const,
  projects: (orgId: string) => ["organisations", orgId, "projects"] as const,
  project: (id: string) => ["projects", id] as const,
  projectSettings: (id: string) => ["projects", id, "settings"] as const,
  crawls: (orgId: string) => ["organisations", orgId, "crawls"] as const,
  crawl: (id: string) => ["crawls", id] as const,
};

export function useHealth() {
  return useQuery({ queryKey: keys.health, queryFn: () => api<Health>("/health") });
}

export function useOrganisations(enabled = true) {
  return useQuery({
    queryKey: keys.organisations,
    queryFn: () => api<Page<Organisation>>("/organisations", { query: { page_size: 100 } }),
    enabled,
  });
}

export function useOrganisation(id: string | null) {
  return useQuery({
    queryKey: keys.organisation(id ?? ""),
    queryFn: () => api<Organisation>(`/organisations/${id}`),
    enabled: !!id,
  });
}

export function useMembers(orgId: string | null, enabled = true) {
  return useQuery({
    queryKey: keys.members(orgId ?? ""),
    queryFn: () => api<Page<Member>>(`/organisations/${orgId}/members`, { query: { page_size: 100 } }),
    enabled: !!orgId && enabled,
  });
}

export function useAuditLogs(orgId: string | null, page: number, enabled = true) {
  return useQuery({
    queryKey: keys.audit(orgId ?? "", page),
    queryFn: () =>
      api<Page<AuditLogEntry>>(`/organisations/${orgId}/audit-logs`, {
        query: { page, page_size: 20 },
      }),
    enabled: !!orgId && enabled,
  });
}

export interface ProjectQuery {
  q?: string;
  sort?: "name" | "created_at" | "domain";
  order?: "asc" | "desc";
  page?: number;
}

export function useProjects(orgId: string | null, params: ProjectQuery = {}, enabled = true) {
  return useQuery({
    queryKey: [...keys.projects(orgId ?? ""), params],
    queryFn: () =>
      api<Page<Project>>(`/organisations/${orgId}/projects`, {
        query: { page_size: 25, ...params },
      }),
    enabled: !!orgId && enabled,
  });
}

export function useProject(id: string) {
  return useQuery({ queryKey: keys.project(id), queryFn: () => api<Project>(`/projects/${id}`) });
}

export function useProjectSettings(id: string) {
  return useQuery({
    queryKey: keys.projectSettings(id),
    queryFn: () => api<ProjectSettings>(`/projects/${id}/settings`),
  });
}

export function isActiveCrawl(job: CrawlJob | undefined | null): boolean {
  return !!job && ACTIVE_CRAWL_STATUSES.includes(job.status);
}

export interface CrawlListQuery {
  project_id?: string;
  status?: string;
  page?: number;
  page_size?: number;
}

export function useCrawls(orgId: string | null, params: CrawlListQuery = {}, enabled = true) {
  return useQuery({
    queryKey: [...keys.crawls(orgId ?? ""), params],
    queryFn: () =>
      api<Page<CrawlJob>>(`/organisations/${orgId}/crawls`, { query: { page_size: 20, ...params } }),
    enabled: !!orgId && enabled,
    // Keep polling while any listed crawl is still in progress.
    refetchInterval: (query) =>
      query.state.data?.items.some((job) => isActiveCrawl(job)) ? 2000 : false,
  });
}

export function useCrawl(id: string) {
  return useQuery({
    queryKey: keys.crawl(id),
    queryFn: () => api<CrawlJob>(`/crawls/${id}`),
    refetchInterval: (query) => (isActiveCrawl(query.state.data) ? 2000 : false),
  });
}

export function useCrawlSummary(id: string, version: string) {
  return useQuery({
    queryKey: [...keys.crawl(id), "summary", version],
    queryFn: () => api<CrawlSummary>(`/crawls/${id}/summary`),
  });
}

export interface PageFilters {
  status_class?: string;
  fetch_status?: string;
  q?: string;
  in_sitemap?: string;
  orphan?: string;
  noindex?: string;
  sort?: string;
  order?: string;
  page?: number;
}

export function useCrawlPages(id: string | null, filters: PageFilters, version: string) {
  return useQuery({
    queryKey: [...keys.crawl(id ?? ""), "pages", filters, version],
    queryFn: () =>
      api<Page<CrawlPageRow>>(`/crawls/${id}/pages`, { query: { page_size: 50, ...filters } }),
    enabled: !!id,
  });
}

export function useCrawlPage(crawlId: string, pageId: string) {
  return useQuery({
    queryKey: [...keys.crawl(crawlId), "page", pageId],
    queryFn: () => api<CrawlPageDetail>(`/crawls/${crawlId}/pages/${pageId}`),
  });
}

export function useBrokenLinks(id: string, page: number, version: string) {
  return useQuery({
    queryKey: [...keys.crawl(id), "broken", page, version],
    queryFn: () => api<Page<BrokenLink>>(`/crawls/${id}/broken-links`, { query: { page, page_size: 25 } }),
  });
}
