import type { Metadata } from "next";

import { ApprovalsView } from "@/components/views/approvals-view";

export const metadata: Metadata = { title: "Approvals" };

export default function Page() {
  return <ApprovalsView />;
}
