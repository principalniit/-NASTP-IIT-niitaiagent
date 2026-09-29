import type { Metadata } from "next";

import { ReportDetailView } from "@/components/views/report-detail-view";

export const metadata: Metadata = { title: "Report" };

export default async function ReportPage(props: PageProps<"/reports/[reportId]">) {
  const { reportId } = await props.params;
  return <ReportDetailView reportId={reportId} />;
}
