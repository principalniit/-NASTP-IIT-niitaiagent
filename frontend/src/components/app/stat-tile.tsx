import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * A metric tile. When `value` is null the tile shows why no number exists instead of a
 * placeholder, so dashboards never display invented figures.
 */
export function StatTile({
  label,
  value,
  emptyText,
  loading,
  hint,
}: {
  label: string;
  value: string | number | null;
  emptyText?: string;
  loading?: boolean;
  hint?: string;
}) {
  return (
    <Card role="group" aria-label={label}>
      <CardHeader className="pb-2">
        <CardDescription>{label}</CardDescription>
        {loading ? (
          <Skeleton className="h-8 w-16" />
        ) : value === null ? (
          <CardTitle className="text-sm font-normal text-muted-foreground">
            {emptyText ?? "No data yet"}
          </CardTitle>
        ) : (
          <CardTitle className="text-3xl font-semibold tabular-nums">{value}</CardTitle>
        )}
      </CardHeader>
      {hint ? <CardContent className="text-xs text-muted-foreground">{hint}</CardContent> : null}
    </Card>
  );
}
