import type { Metadata } from "next";

import { CrawlDetailView } from "@/components/views/crawl-detail-view";

export const metadata: Metadata = { title: "Crawl" };

export default async function CrawlPage(props: PageProps<"/crawls/[crawlId]">) {
  const { crawlId } = await props.params;
  return <CrawlDetailView crawlId={crawlId} />;
}
