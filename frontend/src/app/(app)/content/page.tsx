import type { Metadata } from "next";

import { ContentView } from "@/components/views/content-view";

export const metadata: Metadata = { title: "Content Opportunities" };

export default function Page() {
  return <ContentView />;
}
