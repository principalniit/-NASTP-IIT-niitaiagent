import {
  Activity,
  BarChart3,
  Bot,
  Braces,
  CheckSquare,
  FileSearch,
  FileText,
  FolderKanban,
  LayoutDashboard,
  Link2,
  ListChecks,
  Network,
  Plug,
  ScrollText,
  Search,
  Settings,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";

export type NavGroup = "Workspace" | "Analyse" | "Improve" | "Track" | "Manage";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  group: NavGroup;
  /** One line for launch tiles; never shown inside the navigation links themselves. */
  description: string;
}

export const NAV_ITEMS: NavItem[] = [
  { href: "/overview", label: "Overview", icon: LayoutDashboard, group: "Workspace", description: "SEO health at a glance" },
  { href: "/projects", label: "Projects", icon: FolderKanban, group: "Workspace", description: "Websites, crawl limits and schedules" },
  { href: "/audit", label: "SEO Audit", icon: FileSearch, group: "Analyse", description: "Scores and top priorities" },
  { href: "/crawls", label: "Crawl Explorer", icon: Network, group: "Analyse", description: "Run crawls and inspect results" },
  { href: "/pages", label: "Pages", icon: FileText, group: "Analyse", description: "Every crawled page, with thumbnails" },
  { href: "/issues", label: "Issues", icon: ListChecks, group: "Analyse", description: "Findings with evidence and fixes" },
  { href: "/search", label: "Search Performance", icon: Search, group: "Analyse", description: "Clicks and impressions from Search Console" },
  { href: "/recommendations", label: "AI Recommendations", icon: Bot, group: "Improve", description: "Grounded AI summaries and answers" },
  { href: "/internal-linking", label: "Internal Linking", icon: Link2, group: "Improve", description: "Link suggestions from your content" },
  { href: "/structured-data", label: "Structured Data", icon: Braces, group: "Improve", description: "JSON-LD and microdata checks" },
  { href: "/content", label: "Content Opportunities", icon: ScrollText, group: "Improve", description: "Outlines and drafts for key pages" },
  { href: "/reports", label: "Reports", icon: BarChart3, group: "Track", description: "Branded HTML and PDF reports" },
  { href: "/monitoring", label: "Monitoring", icon: Activity, group: "Track", description: "Score history and crawl comparison" },
  { href: "/approvals", label: "Approvals", icon: CheckSquare, group: "Track", description: "Drafts waiting for review" },
  { href: "/integrations", label: "Integrations", icon: Plug, group: "Manage", description: "Service records, never auto-connected" },
  { href: "/settings", label: "Settings", icon: Settings, group: "Manage", description: "Organisation, AI and branding" },
  { href: "/administration", label: "Administration", icon: ShieldCheck, group: "Manage", description: "Members, plan and audit log" },
];

export const NAV_GROUPS: NavGroup[] = ["Workspace", "Analyse", "Improve", "Track", "Manage"];
