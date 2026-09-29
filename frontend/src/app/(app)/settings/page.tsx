import type { Metadata } from "next";

import { OrgSettingsView } from "@/components/views/org-settings-view";

export const metadata: Metadata = { title: "Settings" };

export default function SettingsPage() {
  return <OrgSettingsView />;
}
