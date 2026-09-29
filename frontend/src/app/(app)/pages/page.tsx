import type { Metadata } from "next";

import { PagesView } from "@/components/views/pages-view";

export const metadata: Metadata = { title: "Pages" };

export default function PagesPage() {
  return <PagesView />;
}
