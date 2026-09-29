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
}

export const NAV_ITEMS: NavItem[] = [
  { href: "/overview", label: "Overview", icon: LayoutDashboard },
  { href: "/projects", label: "Projects", icon: FolderKanban },
  { href: "/audit", label: "SEO Audit", icon: FileSearch },
  { href: "/crawls", label: "Crawl Explorer", icon: Network },
  { href: "/pages", label: "Pages", icon: FileText },
  { href: "/issues", label: "Issues", icon: ListChecks },
  { href: "/recommendations", label: "AI Recommendations", icon: Bot },
  { href: "/internal-linking", label: "Internal Linking", icon: Link2 },
  { href: "/structured-data", label: "Structured Data", icon: Braces },
  { href: "/content", label: "Content Opportunities", icon: ScrollText },
  { href: "/reports", label: "Reports", icon: BarChart3 },
  { href: "/monitoring", label: "Monitoring", icon: Activity },
  { href: "/approvals", label: "Approvals", icon: CheckSquare },
  { href: "/integrations", label: "Integrations", icon: Plug },
  { href: "/settings", label: "Settings", icon: Settings },
  { href: "/administration", label: "Administration", icon: ShieldCheck },
];

