import type { Metadata } from "next";

import { IntegrationsView } from "@/components/views/integrations-view";

export const metadata: Metadata = { title: "Integrations" };

export default function Page() {
  return <IntegrationsView />;
}
