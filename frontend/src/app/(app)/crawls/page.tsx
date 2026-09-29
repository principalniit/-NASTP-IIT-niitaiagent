import type { Metadata } from "next";

import { CrawlsView } from "@/components/views/crawls-view";

export const metadata: Metadata = { title: "Crawl Explorer" };

export default function CrawlsPage() {
  return <CrawlsView />;
}
