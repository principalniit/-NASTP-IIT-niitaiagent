import type { Metadata } from "next";

import { SeoAuditView } from "@/components/views/seo-audit-view";

export const metadata: Metadata = { title: "SEO Audit" };

export default function Page() {
  return <SeoAuditView />;
}
