// Mirrors backend Pydantic schemas (backend/app/modules/*/schemas.py).

export type OrgRole = "owner" | "admin" | "seo_manager" | "editor" | "viewer";

export const ROLE_LABELS: Record<OrgRole, string> = {
  owner: "Owner",
  admin: "Administrator",
  seo_manager: "SEO Manager",
  editor: "Editor",
  viewer: "Viewer",
};

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  is_platform_admin: boolean;
  created_at: string;
}

export interface Membership {
  organisation_id: string;
  organisation_name: string;
  organisation_slug: string;
  role: OrgRole;
  permissions: string[];
}

export interface Me {
  user: User;
  memberships: Membership[];
}

export interface OrganisationSettings {
  brand_tone: string | null;
  approved_terminology: { preferred: string; avoid: string[]; note: string | null }[];
  ai: { provider: "none" | "ollama"; model: string | null };
  crawl_limits: { max_pages: number; max_depth: number; max_concurrency: number };
  report_branding: { primary_colour: string | null; footer_text: string | null };
  notifications: { enabled: boolean; events: string[] };
}

export interface Organisation {
  id: string;
  name: string;
  slug: string;
  domain: string | null;
  logo_url: string | null;
  timezone: string;
  language: string;
  settings: OrganisationSettings;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  my_role: OrgRole | null;
  my_permissions: string[];
}

export interface Member {
  id: string;
  user: { id: string; email: string; full_name: string };
  role: OrgRole;
  created_at: string;
}

export interface Project {
  id: string;
  organisation_id: string;
  name: string;
  root_url: string;
  domain: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface CrawlSettings {
  max_pages: number;
  max_depth: number;
  concurrency: number;
  timeout_seconds: number;
  delay_ms: number;
  user_agent: string;
  render_javascript: boolean;
}

export interface ContentType {
  key: string;
  label: string;
  url_patterns: string[];
  expected_sections: string[];
}

export interface ProjectSettingsData {
  crawl: CrawlSettings;
  allowed_extra_hosts: string[];
  excluded_paths: string[];
  important_pages: string[];
  page_groups: { name: string; patterns: string[] }[];
  content_types: ContentType[];
  institutional_profile: {
    description: string | null;
    contact: { email: string | null; phone: string | null; address: string | null };
    approved_sources: { label: string; url: string }[];
  };
  editorial_approval_required: boolean;
}

export interface ProjectSettings {
  project_id: string;
  settings: ProjectSettingsData;
  updated_at: string;
}

export interface AuditLogEntry {
  id: string;
  created_at: string;
  actor_user_id: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  details: Record<string, unknown>;
  ip_address: string | null;
  request_id: string | null;
}

export interface Health {
  status: "ok" | "degraded";
  database: "ok" | "unavailable";
  ai: { provider: string; status: "disabled" | "available" | "unavailable"; detail: string | null };
  version: string;
}

export type CrawlStatus = "queued" | "running" | "cancelling" | "completed" | "failed" | "cancelled";
export const ACTIVE_CRAWL_STATUSES: CrawlStatus[] = ["queued", "running", "cancelling"];

export type FetchStatus =
  | "fetched"
  | "not_modified"
  | "blocked_by_robots"
  | "blocked_destination"
  | "redirect_out_of_scope"
  | "skipped_content_type"
  | "too_large"
  | "error";

export const FETCH_STATUS_LABELS: Record<FetchStatus, string> = {
  fetched: "Fetched",
  not_modified: "Not modified",
  blocked_by_robots: "Blocked by robots.txt",
  blocked_destination: "Blocked destination",
  redirect_out_of_scope: "Redirects off-site",
  skipped_content_type: "Not HTML",
  too_large: "Too large",
  error: "Error",
};

export interface CrawlJob {
  id: string;
  project_id: string;
  project_name: string | null;
  status: CrawlStatus;
  incremental: boolean;
  previous_crawl_id: string | null;
  config: { max_pages: number; max_depth: number; root_url: string; [key: string]: unknown };
  pages_discovered: number;
  pages_crawled: number;
  pages_failed: number;
  pages_blocked: number;
  robots_status: string | null;
  sitemaps: { url: string; status: string; url_count: number; error: string | null; kind?: string }[];
  sitemap_url_count: number;
  warnings: string[];
  error_message: string | null;
  analysis_status: AnalysisStatus;
  analysed_at: string | null;
  analysis_error: string | null;
  requested_by_id: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface CrawlPageRow {
  id: string;
  url: string;
  final_url: string | null;
  status_code: number | null;
  fetch_status: FetchStatus;
  depth: number | null;
  discovered_via: string;
  content_type: string | null;
  title: string | null;
  word_count: number | null;
  response_time_ms: number | null;
  h1_count: number;
  images_missing_alt: number;
  internal_links_count: number;
  inlinks_count: number;
  is_noindex: boolean;
  in_sitemap: boolean;
  is_orphan: boolean;
}

export interface CrawlLinkRef {
  url: string;
  anchor_text: string | null;
  nofollow: boolean;
  is_internal: boolean;
  page_id: string | null;
  status_code: number | null;
}

export interface JsonLdBlock {
  valid: boolean;
  error: string | null;
  types: string[];
  data: unknown;
}

export interface CrawlPageDetail extends CrawlPageRow {
  error: string | null;
  content_length: number | null;
  redirect_chain: { url: string; status_code: number; elapsed_ms: number }[];
  title_count: number;
  meta_description: string | null;
  meta_description_count: number;
  meta_robots: string | null;
  x_robots_tag: string | null;
  is_nofollow: boolean;
  canonical_url: string | null;
  canonical_count: number;
  lang: string | null;
  headings: { level: number; text: string }[];
  content_hash: string | null;
  images: { src: string; alt: string | null; has_alt: boolean }[];
  image_count: number;
  structured_data: { json_ld?: JsonLdBlock[]; microdata?: { count: number; types: string[] } };
  hreflang: { hreflang: string; href: string }[];
  external_links_count: number;
  fetched_at: string | null;
  outlinks: CrawlLinkRef[];
  inlinks: CrawlLinkRef[];
}

export interface CrawlSummary {
  pages_total: number;
  status_classes: Record<string, number>;
  fetch_statuses: Record<string, number>;
  average_response_time_ms: number | null;
  slowest_response_time_ms: number | null;
  noindex_pages: number;
  pages_in_sitemap: number;
  orphan_pages: number;
  broken_internal_links: number;
  redirects: number;
  duplicate_content_groups: { content_hash: string; urls: string[] }[];
}

export interface BrokenLink {
  source_page_id: string;
  source_url: string;
  target_page_id: string;
  target_url: string;
  anchor_text: string | null;
  status_code: number | null;
  fetch_status: FetchStatus;
}

export type AnalysisStatus = "none" | "queued" | "running" | "completed" | "failed";
export type Severity = "critical" | "high" | "medium" | "low" | "informational";
export const SEVERITIES: Severity[] = ["critical", "high", "medium", "low", "informational"];
export type IssueCategory = "technical" | "on_page" | "content" | "internal_linking" | "structured_data";
export const CATEGORY_LABELS: Record<IssueCategory, string> = {
  technical: "Technical",
  on_page: "On-page",
  content: "Content",
  internal_linking: "Internal linking",
  structured_data: "Structured data",
};
export type ResolutionStatus = "open" | "resolved" | "ignored";

export interface PriorityFactor {
  factor: string;
  points?: number;
  multiplier?: number;
  reason: string;
}

export interface Issue {
  id: string;
  project_id: string;
  rule_id: string;
  scope: "page" | "group" | "site";
  category: IssueCategory;
  severity: Severity;
  title: string;
  description: string;
  recommendation: string;
  evidence: Record<string, unknown>;
  affected_url: string | null;
  affected_urls: string[];
  affected_page_count: number;
  confidence: "high" | "medium" | "low";
  effort: "low" | "medium" | "high";
  priority_score: number;
  priority_breakdown: PriorityFactor[];
  auto_fix_eligible: boolean;
  approval_status: "none" | "pending_review" | "approved" | "rejected";
  resolution_status: ResolutionStatus;
  first_detected_at: string;
  last_detected_at: string;
  first_crawl_id: string | null;
  last_crawl_id: string | null;
  resolved_at: string | null;
  resolved_in_crawl_id: string | null;
  recurrence_count: number;
  triage_note: string | null;
}

export interface IssueSummary {
  latest_crawl_id: string | null;
  analysed_at: string | null;
  open_total: number;
  open_by_severity: Record<Severity, number>;
  open_by_category: Record<IssueCategory, number>;
  ignored_total: number;
  resolved_total: number;
  new_in_latest: number;
  resolved_in_latest: number;
}

export interface ScoreContribution {
  rule_id: string;
  findings: number;
  affected_pages: number;
  penalty: number;
}

export interface CategoryBreakdown {
  score: number | null;
  weight: number;
  pages_considered: number;
  penalty?: number;
  note?: string;
  contributions: ScoreContribution[];
}

export interface Score {
  crawl_job_id: string;
  overall: number | null;
  technical: number | null;
  on_page: number | null;
  content: number | null;
  internal_linking: number | null;
  structured_data: number | null;
  pages_analysed: number;
  breakdown: {
    method: string;
    categories: Record<IssueCategory, CategoryBreakdown>;
    overall: { score: number | null; weights_used: Record<string, number> };
  };
  created_at: string;
}

export interface SchemaFinding {
  id: string;
  page_id: string;
  page_url: string;
  format: string;
  schema_types: string[];
  is_valid: boolean;
  errors: string[];
  warnings: string[];
}

export interface LinkRecommendation {
  id: string;
  source_page_id: string;
  source_url: string;
  source_title: string | null;
  target_page_id: string;
  target_url: string;
  target_title: string | null;
  anchor_text: string;
  reason: string;
  snippet: string | null;
  relevance: number;
}
