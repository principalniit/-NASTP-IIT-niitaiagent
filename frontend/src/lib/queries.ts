"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import {
  ACTIVE_CRAWL_STATUSES,
  type AIAnalysis,
  type AIAnalysisSummary,
  type AIKind,
  type AIStatus,
  type Draft,
  type DraftDetail,
  type DraftStatus,
  type Comparison,
  type Integration,
  type IntegrationProvider,
  type Plan,
  type Usage,
  type Recommendation,
  type RecommendationStatus,
  type Report,
  type Schedule,
  type ScorePoint,
  type Issue,
  type IssueSummary,
  type LinkRecommendation,
  type SchemaFinding,
  type Score,
  type BrokenLink,
  type CrawlJob,
  type CrawlPageDetail,
  type CrawlPageRow,
  type CrawlSummary,
} from "@/lib/types";
import type {
  AuditLogEntry,
  PageSearchPerformance,
  SearchPerformance,
  SearchSync,
  Health,
  Invitation,
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
  invitations: (orgId: string) => ["organisations", orgId, "invitations"] as const,
  audit: (orgId: string, page: number) => ["organisations", orgId, "audit", page] as const,
  projects: (orgId: string) => ["organisations", orgId, "projects"] as const,
  project: (id: string) => ["projects", id] as const,
  projectSettings: (id: string) => ["projects", id, "settings"] as const,
  crawls: (orgId: string) => ["organisations", orgId, "crawls"] as const,
  crawl: (id: string) => ["crawls", id] as const,
  issues: (projectId: string) => ["projects", projectId, "issues"] as const,
  issue: (id: string) => ["issues", id] as const,
  aiStatus: (orgId: string) => ["organisations", orgId, "ai-status"] as const,
  analyses: (projectId: string) => ["projects", projectId, "ai-analyses"] as const,
  analysis: (id: string) => ["ai-analyses", id] as const,
  searchPerformance: (projectId: string, days: number) => ["projects", projectId, "search", days] as const,
  pageSearch: (projectId: string, url: string) => ["projects", projectId, "search", "page", url] as const,
  searchSyncs: (integrationId: string) => ["integrations", integrationId, "search-syncs"] as const,
  recommendations: (projectId: string) => ["projects", projectId, "recommendations"] as const,
  drafts: (projectId: string) => ["projects", projectId, "drafts"] as const,
  draft: (id: string) => ["drafts", id] as const,
  reports: (projectId: string) => ["projects", projectId, "reports"] as const,
  schedule: (projectId: string) => ["projects", projectId, "schedule"] as const,
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

export function useInvitations(orgId: string, enabled = true) {
  return useQuery({
    queryKey: keys.invitations(orgId),
    queryFn: () => api<Invitation[]>(`/organisations/${orgId}/invitations`),
    enabled,
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
  analysed?: boolean;
  page?: number;
  page_size?: number;
}

export function useCrawls(orgId: string | null, params: CrawlListQuery = {}, enabled = true) {
  return useQuery({
    queryKey: [...keys.crawls(orgId ?? ""), params],
    queryFn: () =>
      api<Page<CrawlJob>>(`/organisations/${orgId}/crawls`, {
        query: {
          page_size: 20,
          ...params,
          analysed: params.analysed === undefined ? undefined : String(params.analysed),
        },
      }),
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
    refetchInterval: (query) => {
      const job = query.state.data;
      const analysing = job?.analysis_status === "queued" || job?.analysis_status === "running";
      return isActiveCrawl(job) || analysing ? 2000 : false;
    },
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

export interface IssueFilters {
  status?: string;
  all_statuses?: string;
  severity?: string;
  category?: string;
  rule_id?: string;
  q?: string;
  sort?: string;
  order?: string;
  page?: number;
  page_size?: number;
}

export function useIssues(projectId: string | null, filters: IssueFilters, enabled = true) {
  return useQuery({
    queryKey: [...keys.issues(projectId ?? ""), filters],
    queryFn: () => api<Page<Issue>>(`/projects/${projectId}/issues`, { query: { page_size: 25, ...filters } }),
    enabled: !!projectId && enabled,
  });
}

export function useIssueSummary(projectId: string | null, enabled = true) {
  return useQuery({
    queryKey: [...keys.issues(projectId ?? ""), "summary"],
    queryFn: () => api<IssueSummary>(`/projects/${projectId}/issues/summary`),
    enabled: !!projectId && enabled,
  });
}

export function useIssue(id: string) {
  return useQuery({ queryKey: keys.issue(id), queryFn: () => api<Issue>(`/issues/${id}`) });
}

export function useScore(crawlId: string | null) {
  return useQuery({
    queryKey: [...keys.crawl(crawlId ?? ""), "score"],
    queryFn: () => api<Score>(`/crawls/${crawlId}/score`),
    enabled: !!crawlId,
  });
}

export function useSchemaFindings(crawlId: string | null, page: number, invalidOnly: boolean) {
  return useQuery({
    queryKey: [...keys.crawl(crawlId ?? ""), "schema", page, invalidOnly],
    queryFn: () =>
      api<Page<SchemaFinding>>(`/crawls/${crawlId}/schema-findings`, {
        query: { page, page_size: 25, invalid_only: invalidOnly ? "true" : undefined },
      }),
    enabled: !!crawlId,
  });
}

export function useLinkRecommendations(crawlId: string | null, page: number) {
  return useQuery({
    queryKey: [...keys.crawl(crawlId ?? ""), "link-recommendations", page],
    queryFn: () =>
      api<Page<LinkRecommendation>>(`/crawls/${crawlId}/link-recommendations`, { query: { page, page_size: 25 } }),
    enabled: !!crawlId,
  });
}

/** The most recent crawl of a project whose analysis completed. */
export function useLatestAnalysedCrawl(orgId: string | null, projectId: string | null) {
  const query = useCrawls(orgId, { project_id: projectId ?? undefined, analysed: true, page_size: 1 }, !!projectId);
  return { ...query, crawl: query.data?.items[0] ?? null };
}

// ---------------------------------------------------------------- AI assistant

export function useAIStatus(orgId: string | null) {
  return useQuery({
    queryKey: keys.aiStatus(orgId ?? ""),
    queryFn: () => api<AIStatus>(`/organisations/${orgId}/ai/status`),
    enabled: !!orgId,
    staleTime: 60_000,
  });
}

function running(status: string | undefined): boolean {
  return status === "queued" || status === "running";
}

export interface AnalysisFilters {
  kind?: AIKind;
  subject_id?: string;
  page_url?: string;
  page_size?: number;
}

export function useAnalyses(projectId: string | null, filters: AnalysisFilters = {}, enabled = true) {
  return useQuery({
    queryKey: [...keys.analyses(projectId ?? ""), filters],
    queryFn: () =>
      api<Page<AIAnalysisSummary>>(`/projects/${projectId}/ai/analyses`, { query: { page_size: 10, ...filters } }),
    enabled: !!projectId && enabled,
    refetchInterval: (query) => (query.state.data?.items.some((a) => running(a.status)) ? 2000 : false),
  });
}

/** One AI analysis, polled while the worker is still running it. */
export function useAnalysis(id: string | null) {
  return useQuery({
    queryKey: keys.analysis(id ?? ""),
    queryFn: () => api<AIAnalysis>(`/ai-analyses/${id}`),
    enabled: !!id,
    refetchInterval: (query) => (running(query.state.data?.status) ? 2000 : false),
  });
}

export function useRecommendations(projectId: string | null, status: RecommendationStatus | "" = "open", page = 1) {
  return useQuery({
    queryKey: [...keys.recommendations(projectId ?? ""), status, page],
    queryFn: () =>
      api<Page<Recommendation>>(`/projects/${projectId}/recommendations`, {
        query: { status_filter: status || undefined, page, page_size: 20 },
      }),
    enabled: !!projectId,
  });
}

// ---------------------------------------------------------------- drafts

export interface DraftFilters {
  status_filter?: DraftStatus | "";
  page_url?: string;
  page?: number;
}

export function useDrafts(projectId: string | null, filters: DraftFilters = {}) {
  return useQuery({
    queryKey: [...keys.drafts(projectId ?? ""), filters],
    queryFn: () => api<Page<Draft>>(`/projects/${projectId}/drafts`, { query: { page_size: 25, ...filters } }),
    enabled: !!projectId,
  });
}

export function useDraft(id: string) {
  return useQuery({ queryKey: keys.draft(id), queryFn: () => api<DraftDetail>(`/drafts/${id}`) });
}

// ---------------------------------------------------------------- reports and monitoring

export function useReports(projectId: string | null, page = 1) {
  return useQuery({
    queryKey: [...keys.reports(projectId ?? ""), page],
    queryFn: () => api<Page<Report>>(`/projects/${projectId}/reports`, { query: { page, page_size: 20 } }),
    enabled: !!projectId,
    refetchInterval: (query) => (query.state.data?.items.some((r) => running(r.status)) ? 2000 : false),
  });
}

export function useSchedule(projectId: string) {
  return useQuery({ queryKey: keys.schedule(projectId), queryFn: () => api<Schedule>(`/projects/${projectId}/schedule`) });
}

export function useScoreHistory(projectId: string | null) {
  return useQuery({
    queryKey: ["projects", projectId ?? "", "score-history"],
    queryFn: () => api<ScorePoint[]>(`/projects/${projectId}/scores`),
    enabled: !!projectId,
  });
}

export function useComparison(projectId: string | null, fromCrawl?: string, toCrawl?: string, enabled = true) {
  return useQuery({
    queryKey: ["projects", projectId ?? "", "compare", fromCrawl ?? "", toCrawl ?? ""],
    queryFn: () =>
      api<Comparison>(`/projects/${projectId}/compare`, { query: { from_crawl: fromCrawl, to_crawl: toCrawl } }),
    enabled: !!projectId && enabled,
    retry: false,
  });
}

// ---------------------------------------------------------------- plans, integrations, platform audit

export function useUsage(orgId: string | null) {
  return useQuery({
    queryKey: ["organisations", orgId ?? "", "usage"],
    queryFn: () => api<Usage>(`/organisations/${orgId}/usage`),
    enabled: !!orgId,
  });
}

export function usePlans(enabled: boolean) {
  return useQuery({ queryKey: ["plans"], queryFn: () => api<Plan[]>("/plans"), enabled });
}

export function useIntegrationProviders() {
  return useQuery({
    queryKey: ["integration-providers"],
    queryFn: () => api<IntegrationProvider[]>("/integration-providers"),
    staleTime: Infinity,
  });
}

export function useIntegrations(orgId: string | null, enabled = true) {
  return useQuery({
    queryKey: ["organisations", orgId ?? "", "integrations"],
    queryFn: () => api<Integration[]>(`/organisations/${orgId}/integrations`),
    enabled: !!orgId && enabled,
  });
}

export function useEncryptionStatus(orgId: string | null, enabled = true) {
  return useQuery({
    queryKey: ["organisations", orgId ?? "", "integrations", "encryption"],
    queryFn: () => api<{ available: boolean }>(`/organisations/${orgId}/integrations/encryption`),
    enabled: !!orgId && enabled,
  });
}

export function usePlatformAudit(page: number, platformOnly: boolean, enabled: boolean) {
  return useQuery({
    queryKey: ["admin", "audit", page, platformOnly],
    queryFn: () =>
      api<Page<AuditLogEntry>>("/admin/audit-logs", {
        query: { page, page_size: 20, platform_only: platformOnly ? "true" : undefined },
      }),
    enabled,
  });
}

/** Google Search Console figures for a project; never estimated. */
export function useSearchPerformance(projectId: string | null, days = 28) {
  return useQuery({
    queryKey: keys.searchPerformance(projectId ?? "", days),
    queryFn: () => api<SearchPerformance>(`/projects/${projectId}/search-performance`, { query: { days } }),
    enabled: !!projectId,
  });
}

export function usePageSearchPerformance(projectId: string | null, url: string | null) {
  return useQuery({
    queryKey: keys.pageSearch(projectId ?? "", url ?? ""),
    queryFn: () => api<PageSearchPerformance>(`/projects/${projectId}/search-performance/page`, { query: { url: url ?? "" } }),
    enabled: !!projectId && !!url,
  });
}

export function useSearchSyncs(integrationId: string, enabled = true) {
  return useQuery({
    queryKey: keys.searchSyncs(integrationId),
    queryFn: () => api<SearchSync[]>(`/integrations/${integrationId}/search-console/syncs`),
    enabled,
    refetchInterval: (query) =>
      query.state.data?.some((s) => s.status === "queued" || s.status === "running") ? 3000 : false,
  });
}
