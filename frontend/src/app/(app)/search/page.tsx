import type { Metadata } from "next";

import { SearchPerformanceView } from "@/components/views/search-performance-view";

export const metadata: Metadata = { title: "Search Performance" };

export default function Page() {
  return <SearchPerformanceView />;
}
