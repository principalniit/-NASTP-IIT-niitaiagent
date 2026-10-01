import type { Metadata } from "next";

import { InviteView } from "@/components/views/invite-view";

export const metadata: Metadata = { title: "Accept invitation" };

export default function InvitePage() {
  return <InviteView />;
}
