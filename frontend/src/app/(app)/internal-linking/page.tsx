import type { Metadata } from "next";

import { InternalLinkingView } from "@/components/views/internal-linking-view";

export const metadata: Metadata = { title: "Internal Linking" };

export default function Page() {
  return <InternalLinkingView />;
}
