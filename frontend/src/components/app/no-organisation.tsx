import { EmptyState } from "@/components/app/states";

export function NoOrganisation() {
  return (
    <EmptyState
      title="You are not a member of any organisation yet"
      description="Ask an organisation owner or administrator to add you. Platform administrators can create organisations from the command line or the API."
    />
  );
}
