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
  Settings,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Phase that delivers this section. Undefined means available now. */
  phase?: number;
  summary?: string;
}

export const NAV_ITEMS: NavItem[] = [
  { href: "/overview", label: "Overview", icon: LayoutDashboard },
  { href: "/projects", label: "Projects", icon: FolderKanban },
  { href: "/audit", label: "SEO Audit", icon: FileSearch, phase: 3, summary: "Run the deterministic rules engine over a completed crawl and review scored findings." },
  { href: "/crawls", label: "Crawl Explorer", icon: Network, summary: "Start crawls, follow progress, and inspect status codes, redirects and response times." },
  { href: "/pages", label: "Pages", icon: FileText, summary: "Browse every crawled page with its metadata, headings, links and structured data." },
  { href: "/issues", label: "Issues", icon: ListChecks, phase: 3, summary: "Prioritised SEO issues with evidence, affected URLs and resolution tracking." },
  { href: "/recommendations", label: "AI Recommendations", icon: Bot, phase: 4, summary: "Grounded explanations and recommendations generated from verified crawl evidence." },
  { href: "/internal-linking", label: "Internal Linking", icon: Link2, phase: 3, summary: "Incoming and outgoing link counts, orphan pages and relevant linking opportunities." },
  { href: "/structured-data", label: "Structured Data", icon: Braces, phase: 3, summary: "Detected JSON-LD and microdata, validation errors and optional schema enhancements." },
  { href: "/content", label: "Content Opportunities", icon: ScrollText, phase: 4, summary: "Thin, duplicate and overlapping content, with drafts that require human approval." },
  { href: "/reports", label: "Reports", icon: BarChart3, phase: 5, summary: "Management reports in HTML and PDF with methodology and limitations." },
  { href: "/monitoring", label: "Monitoring", icon: Activity, phase: 5, summary: "Crawl-to-crawl comparisons, score history and verified issue resolution." },
  { href: "/approvals", label: "Approvals", icon: CheckSquare, phase: 4, summary: "Review, approve or reject proposed content changes with full version history." },
  { href: "/integrations", label: "Integrations", icon: Plug, phase: 6, summary: "Optional providers such as Search Console and CMS connections, off by default." },
  { href: "/settings", label: "Settings", icon: Settings },
  { href: "/administration", label: "Administration", icon: ShieldCheck },
];

export function findNavItem(href: string): NavItem | undefined {
  return NAV_ITEMS.find((item) => item.href === href);
}
