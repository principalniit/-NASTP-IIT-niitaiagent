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
  report_branding: {
    primary_colour: string | null;
    footer_text: string | null;
    display_name?: string | null;
    cover_note?: string | null;
  };
  data_retention?: { keep_crawls: number | null; delete_reports_after_days: number | null };
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

export interface Invitation {
  id: string;
  email: string;
  role: OrgRole;
  expires_at: string;
  created_at: string;
}

export interface InvitationCreated {
  invitation: Invitation;
  /** Shown once: the token is not stored in readable form. */
  invite_url: string;
  email_sent: boolean;
}

export interface InvitationPreview {
  organisation_name: string;
  email: string;
  role: OrgRole;
  expires_at: string;
  account_exists: boolean;
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
  organisation_id?: string | null;
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
  pages_pruned_at?: string | null;
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
  /** Analysed after running the page's scripts (project setting). */
  rendered_with_js: boolean;
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

// ---------------------------------------------------------------- AI assistant

export type AIKind =
  | "management_summary"
  | "issue_explanation"
  | "page_plan"
  | "metadata_draft"
  | "content_outline"
  | "question";
export type AIRunStatus = "queued" | "running" | "completed" | "failed";

export interface AIStatus {
  enabled: boolean;
  provider: string;
  model: string | null;
  status: "disabled" | "available" | "unavailable";
  detail: string | null;
}

export interface AIRequest {
  kind: AIKind;
  issue_id?: string;
  page_url?: string;
  question?: string;
  goal?: string;
}

export interface AIAnalysisSummary {
  id: string;
  project_id: string;
  crawl_job_id: string | null;
  kind: AIKind;
  status: AIRunStatus;
  subject_type: string;
  subject_id: string | null;
  params: Record<string, string>;
  provider: string | null;
  model: string | null;
  error: string | null;
  created_at: string;
  finished_at: string | null;
  requested_by_id: string | null;
}

export interface Grounding {
  passed?: boolean;
  violations?: string[];
  warnings?: string[];
}

export interface AIAnalysis extends AIAnalysisSummary {
  prompt_version: string | null;
  evidence: Record<string, unknown>;
  output: Record<string, unknown> | null;
  grounding: Grounding;
  attempts: number;
  duration_ms: number | null;
  /** What the model did, as Ollama reported it; null when the model was never called. */
  metrics: AIUsage | null;
  draft_ids: string[];
  /** The signed-in person's own verdict on this result. */
  my_feedback: AIFeedback | null;
}

export type FeedbackRating = "helpful" | "not_helpful";
export type FeedbackReason = "wrong" | "off_topic" | "vague" | "missed_data" | "other";

export interface AIFeedback {
  rating: FeedbackRating;
  reason: FeedbackReason | null;
  comment: string | null;
  updated_at: string;
}

export interface AIUsage {
  calls: number;
  load_ms: number;
  prompt_tokens: number;
  prompt_ms: number;
  output_tokens: number;
  output_ms: number;
  total_ms: number;
}

export type RecommendationStatus = "open" | "accepted" | "dismissed";

export interface Recommendation {
  id: string;
  project_id: string;
  ai_analysis_id: string;
  issue_ids: string[];
  page_url: string | null;
  title: string;
  body: string;
  steps: string[];
  status: RecommendationStatus;
  created_at: string;
}

// ---------------------------------------------------------------- drafts and approvals

export type DraftField = "title" | "meta_description" | "h1" | "content_outline" | "content_section";
export type DraftStatus = "draft" | "pending_review" | "approved" | "rejected" | "published" | "rolled_back";
export type ApprovalAction =
  | "created"
  | "edited"
  | "submitted"
  | "approved"
  | "rejected"
  | "reopened"
  | "published"
  | "rolled_back";

export const DRAFT_FIELD_LABELS: Record<DraftField, string> = {
  title: "Page title",
  meta_description: "Meta description",
  h1: "Main heading (H1)",
  content_outline: "Content outline",
  content_section: "Content section",
};

export const DRAFT_STATUS_LABELS: Record<DraftStatus, string> = {
  draft: "Draft",
  pending_review: "Pending review",
  approved: "Approved",
  rejected: "Rejected",
  published: "Published",
  rolled_back: "Rolled back",
};

export const APPROVAL_ACTION_LABELS: Record<ApprovalAction, string> = {
  created: "Created",
  edited: "Edited",
  submitted: "Submitted for review",
  approved: "Approved",
  rejected: "Rejected",
  reopened: "Reopened",
  published: "Marked as published",
  rolled_back: "Marked as rolled back",
};

export interface Draft {
  id: string;
  project_id: string;
  page_url: string;
  crawl_page_id: string | null;
  field: DraftField;
  original_content: string | null;
  proposed_content: string;
  reason: string;
  evidence: { issue_ids?: string[]; facts_used?: string[]; warnings?: string[] } & Record<string, unknown>;
  source: "ai" | "human";
  ai_analysis_id: string | null;
  status: DraftStatus;
  version: number;
  protected: boolean;
  protected_reasons: string[];
  created_by_id: string | null;
  version_author_id: string | null;
  reviewed_by_id: string | null;
  reviewed_at: string | null;
  source_reference: string | null;
  published_at: string | null;
  rolled_back_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface DraftVersion {
  version: number;
  proposed_content: string;
  reason: string;
  source: "ai" | "human";
  edited_by_id: string | null;
  created_at: string;
}

export interface ApprovalEntry {
  id: string;
  version: number;
  action: ApprovalAction;
  from_status: DraftStatus | null;
  to_status: DraftStatus;
  actor_id: string | null;
  comment: string | null;
  source_reference: string | null;
  created_at: string;
}

export interface DraftDetail extends Draft {
  versions: DraftVersion[];
  trail: ApprovalEntry[];
  people: Record<string, string>;
  /** People who created, requested, wrote or submitted the draft; they cannot approve it. */
  contributor_ids: string[];
}

// ---------------------------------------------------------------- reports and monitoring

export type ReportStatus = "queued" | "running" | "completed" | "failed";
export type PdfStatus = "pending" | "ready" | "unavailable" | "failed";

export interface Report {
  id: string;
  project_id: string;
  crawl_job_id: string | null;
  title: string;
  status: ReportStatus;
  include_ai: boolean;
  pdf_status: PdfStatus;
  pdf_error: string | null;
  error: string | null;
  requested_by_id: string | null;
  created_at: string;
  finished_at: string | null;
}

export type ScheduleFrequency = "daily" | "weekly" | "monthly";

export interface Schedule {
  enabled: boolean;
  frequency: ScheduleFrequency;
  hour: number;
  timezone: string;
  next_run_at: string | null;
  last_run_at: string | null;
  platform_enabled: boolean;
}

export interface ScorePoint {
  crawl_job_id: string;
  created_at: string;
  overall: number | null;
  technical: number | null;
  on_page: number | null;
  content: number | null;
  internal_linking: number | null;
  structured_data: number | null;
}

export interface Capped<T> {
  count: number;
  items: T[];
}

export interface ChangedValue<T> {
  url: string;
  from: T;
  to: T;
}

export interface ComparedIssue {
  id: string;
  rule_id: string;
  title: string;
  severity: Severity;
  affected_url: string | null;
  affected_page_count: number;
}

export interface Comparison {
  from_crawl: { id: string; finished_at: string | null; pages: number; page_data_removed?: boolean };
  to_crawl: { id: string; finished_at: string | null; pages: number; page_data_removed?: boolean };
  score_change: Record<string, { from: number | null; to: number | null; change: number | null }>;
  issues: { new: Capped<ComparedIssue>; resolved: Capped<ComparedIssue>; recurring: Capped<ComparedIssue> };
  pages: {
    added: Capped<string>;
    removed: Capped<string>;
    status_changes: Capped<ChangedValue<number | null>>;
    title_changes: Capped<ChangedValue<string | null>>;
    meta_description_changes: Capped<ChangedValue<string | null>>;
    redirect_changes: Capped<ChangedValue<string | null>>;
    content_changed: Capped<string>;
    inbound_link_changes: Capped<ChangedValue<number>>;
  };
  note: string;
}

// ---------------------------------------------------------------- plans and integrations

export interface PlanLimits {
  max_projects: number | null;
  max_members: number | null;
  max_pages_per_crawl: number | null;
  max_crawls_per_month: number | null;
  max_ai_tasks_per_day: number | null;
  max_reports_per_month: number | null;
}

export interface Plan {
  id: string;
  key: string;
  name: string;
  description: string | null;
  limits: PlanLimits;
  is_default: boolean;
}

export type UsageResource = "projects" | "members" | "crawls_per_month" | "ai_tasks_per_day" | "reports_per_month";

export interface Usage {
  plan: Plan;
  plan_assigned: boolean;
  usage: Record<UsageResource, { used: number; limit: number | null }>;
  max_pages_per_crawl: number | null;
  month_starts: string;
  day_starts: string;
}

export interface IntegrationProvider {
  key: string;
  name: string;
  category: "search_data" | "analytics" | "cms" | "notifications";
  description: string;
  config_schema: { properties: Record<string, { title?: string; type?: string; description?: string; default?: unknown; readOnly?: boolean }>; required?: string[] };
  secret_label: string;
}

export interface Integration {
  id: string;
  provider: string;
  name: string;
  enabled: boolean;
  config: Record<string, unknown>;
  secret_set: boolean;
  secret_hint: string | null;
  connected: boolean;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------- search console

export interface SearchTotals {
  clicks: number;
  impressions: number;
  ctr: number | null;
  /** Average position weighted by impressions; 1 is the top of Google's results. */
  position: number | null;
}

export interface SearchRow {
  clicks: number;
  impressions: number;
  ctr: number | null;
  position: number | null;
}

export interface SearchPerformance {
  state: "not_connected" | "no_data" | "ready";
  connected: boolean;
  properties: string[];
  last_synced_at: string | null;
  start: string | null;
  end: string | null;
  totals: SearchTotals | null;
  daily: { day: string; clicks: number; impressions: number }[];
  top_pages: (SearchRow & { page: string })[];
  top_queries: (SearchRow & { query: string })[];
}

export interface PageSearchPerformance {
  state: "no_data" | "ready";
  start: string | null;
  end: string | null;
  totals: SearchTotals | null;
  top_queries: (SearchRow & { query: string })[];
}

export interface SearchSync {
  id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  start_date: string | null;
  end_date: string | null;
  page_day_rows: number;
  query_rows: number;
  error: string | null;
  created_at: string;
  finished_at: string | null;
}
