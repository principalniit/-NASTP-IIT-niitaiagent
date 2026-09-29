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
