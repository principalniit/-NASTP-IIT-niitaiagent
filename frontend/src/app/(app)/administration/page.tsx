import type { Metadata } from "next";

import { AdministrationView } from "@/components/views/administration-view";

export const metadata: Metadata = { title: "Administration" };

export default function AdministrationPage() {
  return <AdministrationView />;
}
