import type { Metadata } from "next";

import { StructuredDataView } from "@/components/views/structured-data-view";

export const metadata: Metadata = { title: "Structured Data" };

export default function Page() {
  return <StructuredDataView />;
}
