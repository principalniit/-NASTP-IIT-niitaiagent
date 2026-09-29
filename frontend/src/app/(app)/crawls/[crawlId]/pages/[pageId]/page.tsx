import type { Metadata } from "next";

import { PageDetailView } from "@/components/views/page-detail-view";

export const metadata: Metadata = { title: "Page details" };

export default async function CrawledPage(props: PageProps<"/crawls/[crawlId]/pages/[pageId]">) {
  const { crawlId, pageId } = await props.params;
  return <PageDetailView crawlId={crawlId} pageId={pageId} />;
}
