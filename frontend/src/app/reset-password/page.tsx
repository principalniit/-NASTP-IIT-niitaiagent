import type { Metadata } from "next";

import { ResetPasswordView } from "@/components/views/password-reset-view";

export const metadata: Metadata = { title: "Choose a new password" };

export default function ResetPasswordPage() {
  return <ResetPasswordView />;
}
