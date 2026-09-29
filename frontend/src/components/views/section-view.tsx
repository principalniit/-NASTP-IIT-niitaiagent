import { Construction } from "lucide-react";

import { PageHeader } from "@/components/app/page-header";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { NavItem } from "@/lib/navigation";

/** Honest placeholder for sections whose backend has not been built yet. */
export function SectionView({ item }: { item: NavItem }) {
  return (
    <>
      <PageHeader title={item.label} description={item.summary} />
      <Card className="max-w-2xl">
        <CardHeader>
          <div className="flex items-center gap-2">
            <Construction className="size-5 text-muted-foreground" aria-hidden />
            <CardTitle>Not available yet</CardTitle>
            <Badge variant="secondary">Phase {item.phase}</Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-2 text-sm text-muted-foreground">
          <p>This section is delivered in Phase {item.phase} of the implementation plan.</p>
          <p>
            It will only show information derived from real crawls and analyses of your projects.
            No sample or estimated figures are displayed in the meantime.
          </p>
        </CardContent>
      </Card>
    </>
  );
}
