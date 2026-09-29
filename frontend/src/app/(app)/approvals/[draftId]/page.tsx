import type { Metadata } from "next";

import { DraftDetailView } from "@/components/views/draft-detail-view";

export const metadata: Metadata = { title: "Draft" };

export default async function DraftPage(props: PageProps<"/approvals/[draftId]">) {
  const { draftId } = await props.params;
  return <DraftDetailView draftId={draftId} />;
}
