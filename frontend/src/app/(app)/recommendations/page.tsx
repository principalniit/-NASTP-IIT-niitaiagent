import type { Metadata } from "next";

import { RecommendationsView } from "@/components/views/recommendations-view";

export const metadata: Metadata = { title: "AI Recommendations" };

export default function Page() {
  return <RecommendationsView />;
}
