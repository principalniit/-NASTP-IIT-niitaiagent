import type { Metadata } from "next";

import { IssueDetailView } from "@/components/views/issue-detail-view";

export const metadata: Metadata = { title: "Issue" };

export default async function IssuePage(props: PageProps<"/issues/[issueId]">) {
  const { issueId } = await props.params;
  return <IssueDetailView issueId={issueId} />;
}
