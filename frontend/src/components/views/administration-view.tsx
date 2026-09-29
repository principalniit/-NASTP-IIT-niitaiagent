"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, UserPlus } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { describedBy, Field } from "@/components/app/field";
import { NoOrganisation } from "@/components/app/no-organisation";
import { PageHeader } from "@/components/app/page-header";
import { EmptyState, ErrorState, LoadingState } from "@/components/app/states";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { PlanCard } from "@/components/admin/plan-card";
import { PlatformAuditCard } from "@/components/admin/platform-audit-card";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, ApiError } from "@/lib/api";
import { useCurrentOrg } from "@/lib/current-org";
import { applyApiErrors } from "@/lib/form-errors";
import { keys, useAuditLogs, useMembers } from "@/lib/queries";
import { ROLE_LABELS, type Member, type Organisation, type OrgRole } from "@/lib/types";
import { useSession } from "@/lib/session";
import { formatDateTime } from "@/lib/utils";

const ROLES = Object.keys(ROLE_LABELS) as OrgRole[];

export function AdministrationView() {
  const { current, can, isLoading } = useCurrentOrg();
  const { me } = useSession();
  if (isLoading) return <LoadingState />;
  if (!current) return <NoOrganisation />;
  return (
    <>
      <PageHeader title="Administration" description={`Members and audit trail for ${current.name}.`} />
      <div className="space-y-6">
        <MembersCard org={current} canManage={can("members:manage")} />
        <PlanCard org={current} />
        {can("audit:read") ? <AuditCard org={current} /> : null}
        {me?.user.is_platform_admin ? <PlatformAuditCard /> : null}
      </div>
    </>
  );
}

function MembersCard({ org, canManage }: { org: Organisation; canManage: boolean }) {
  const members = useMembers(org.id);
  const queryClient = useQueryClient();
  const { me } = useSession();
  const [actionError, setActionError] = useState<string | null>(null);
  const ownerLevel = org.my_role === "owner" || (org.my_role === null && !!me?.user.is_platform_admin);
  const invalidate = () => queryClient.invalidateQueries({ queryKey: keys.members(org.id) });

  const changeRole = useMutation({
    mutationFn: ({ member, role }: { member: Member; role: OrgRole }) =>
      api<Member>(`/organisations/${org.id}/members/${member.id}`, { method: "PATCH", body: { role } }),
    onSuccess: invalidate,
    onError: (e) => setActionError(e instanceof ApiError ? e.message : "Could not change the role"),
  });
  const remove = useMutation({
    mutationFn: (member: Member) => api<void>(`/organisations/${org.id}/members/${member.id}`, { method: "DELETE" }),
    onSuccess: invalidate,
    onError: (e) => setActionError(e instanceof ApiError ? e.message : "Could not remove the member"),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Members</CardTitle>
        <CardDescription>Roles control what each person can see and change. Access is enforced by the server.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {actionError ? (
          <Alert variant="destructive">
            <AlertDescription>{actionError}</AlertDescription>
          </Alert>
        ) : null}
        {members.isLoading ? (
          <LoadingState />
        ) : members.error ? (
          <ErrorState error={members.error} onRetry={() => void members.refetch()} />
        ) : !members.data?.items.length ? (
          <EmptyState title="No members" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead className="hidden sm:table-cell">Email</TableHead>
                <TableHead>Role</TableHead>
                {canManage ? <TableHead className="text-right">Actions</TableHead> : null}
              </TableRow>
            </TableHeader>
            <TableBody>
              {members.data.items.map((m) => {
                const locked = !ownerLevel && m.role === "owner";
                return (
                  <TableRow key={m.id}>
                    <TableCell className="font-medium">{m.user.full_name}</TableCell>
                    <TableCell className="hidden text-muted-foreground sm:table-cell">{m.user.email}</TableCell>
                    <TableCell>
                      {canManage && !locked ? (
                        <>
                          <label htmlFor={`role-${m.id}`} className="sr-only">
                            Role for {m.user.full_name}
                          </label>
                          <NativeSelect
                            id={`role-${m.id}`}
                            className="h-8 w-40"
                            value={m.role}
                            disabled={changeRole.isPending}
                            onChange={(e) => {
                              setActionError(null);
                              changeRole.mutate({ member: m, role: e.target.value as OrgRole });
                            }}
                          >
                            {ROLES.filter((r) => ownerLevel || r !== "owner").map((r) => (
                              <option key={r} value={r}>
                                {ROLE_LABELS[r]}
                              </option>
                            ))}
                          </NativeSelect>
                        </>
                      ) : (
                        ROLE_LABELS[m.role]
                      )}
                    </TableCell>
                    {canManage ? (
                      <TableCell className="text-right">
                        {!locked ? (
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={remove.isPending}
                            onClick={() => {
                              setActionError(null);
                              if (window.confirm(`Remove ${m.user.full_name} from ${org.name}?`)) remove.mutate(m);
                            }}
                          >
                            Remove<span className="sr-only"> {m.user.full_name}</span>
                          </Button>
                        ) : null}
                      </TableCell>
                    ) : null}
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
        {canManage ? <AddMemberForm org={org} ownerLevel={ownerLevel} /> : null}
      </CardContent>
    </Card>
  );
}

const addSchema = z.object({
  email: z.string().trim().email("Enter a valid email address"),
  role: z.enum(["owner", "admin", "seo_manager", "editor", "viewer"]),
  full_name: z.string().trim().max(200),
  password: z.union([z.literal(""), z.string().min(12, "At least 12 characters").max(128)]),
});
type AddValues = z.infer<typeof addSchema>;

function AddMemberForm({ org, ownerLevel }: { org: Organisation; ownerLevel: boolean }) {
  const queryClient = useQueryClient();
  const [formError, setFormError] = useState<string | null>(null);
  const [needsAccount, setNeedsAccount] = useState(false);
  const form = useForm<AddValues>({
    resolver: zodResolver(addSchema),
    defaultValues: { email: "", role: "viewer", full_name: "", password: "" },
  });
  const add = useMutation({
    mutationFn: (v: AddValues) =>
      api<Member>(`/organisations/${org.id}/members`, {
        method: "POST",
        body: {
          email: v.email,
          role: v.role,
          ...(v.full_name ? { full_name: v.full_name } : {}),
          ...(v.password ? { password: v.password } : {}),
        },
      }),
    onSuccess: () => {
      form.reset();
      setNeedsAccount(false);
      void queryClient.invalidateQueries({ queryKey: keys.members(org.id) });
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code === "account_details_required") {
        setNeedsAccount(true);
        setFormError("No account exists for this email. Enter a name and an initial password to create one.");
        return;
      }
      setFormError(applyApiErrors(error, form.setError, { email: "email", role: "role", full_name: "full_name", password: "password" }));
    },
  });
  const { errors } = form.formState;
  return (
    <form
      noValidate
      className="space-y-4 rounded-lg border bg-muted/30 p-4"
      onSubmit={form.handleSubmit((v) => {
        setFormError(null);
        add.mutate(v);
      })}
    >
      <h3 className="flex items-center gap-2 text-sm font-semibold">
        <UserPlus className="size-4" aria-hidden /> Add a member
      </h3>
      {formError ? (
        <Alert variant={needsAccount ? "default" : "destructive"}>
          <AlertDescription>{formError}</AlertDescription>
        </Alert>
      ) : null}
      <div className="grid gap-4 sm:grid-cols-2">
        <Field id="member-email" label="Email" error={errors.email?.message}>
          <Input id="member-email" type="email" aria-invalid={!!errors.email} aria-describedby={describedBy("member-email", errors.email?.message)} {...form.register("email")} />
        </Field>
        <Field id="member-role" label="Role">
          <NativeSelect id="member-role" {...form.register("role")}>
            {ROLES.filter((r) => ownerLevel || r !== "owner").map((r) => (
              <option key={r} value={r}>
                {ROLE_LABELS[r]}
              </option>
            ))}
          </NativeSelect>
        </Field>
        {needsAccount ? (
          <>
            <Field id="member-name" label="Full name" error={errors.full_name?.message}>
              <Input id="member-name" {...form.register("full_name")} />
            </Field>
            <Field id="member-password" label="Initial password" error={errors.password?.message} hint="Share it securely; the person should change it after first sign-in.">
              <Input id="member-password" type="password" autoComplete="new-password" aria-describedby={describedBy("member-password", errors.password?.message, "hint")} {...form.register("password")} />
            </Field>
          </>
        ) : null}
      </div>
      <Button type="submit" size="sm" disabled={add.isPending}>
        {add.isPending ? "Adding…" : "Add member"}
      </Button>
    </form>
  );
}

function AuditCard({ org }: { org: Organisation }) {
  const [page, setPage] = useState(1);
  const logs = useAuditLogs(org.id, page);
  const totalPages = logs.data ? Math.max(1, Math.ceil(logs.data.total / logs.data.page_size)) : 1;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Audit log</CardTitle>
        <CardDescription>Append-only record of changes and sign-in events for this organisation.</CardDescription>
      </CardHeader>
      <CardContent>
        {logs.isLoading ? (
          <LoadingState />
        ) : logs.error ? (
          <ErrorState error={logs.error} onRetry={() => void logs.refetch()} />
        ) : !logs.data?.items.length ? (
          <EmptyState title="No audit entries yet" />
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>When</TableHead>
                  <TableHead>Action</TableHead>
                  <TableHead className="hidden md:table-cell">Target</TableHead>
                  <TableHead className="hidden lg:table-cell">IP</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {logs.data.items.map((entry) => (
                  <TableRow key={entry.id}>
                    <TableCell className="whitespace-nowrap text-muted-foreground">{formatDateTime(entry.created_at, org.timezone)}</TableCell>
                    <TableCell className="font-mono text-xs">{entry.action}</TableCell>
                    <TableCell className="hidden text-muted-foreground md:table-cell">{entry.target_type ?? "—"}</TableCell>
                    <TableCell className="hidden text-muted-foreground lg:table-cell">{entry.ip_address ?? "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <nav aria-label="Audit log pagination" className="mt-4 flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Page {page} of {totalPages}</span>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                  <ChevronLeft aria-hidden /> Previous
                </Button>
                <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
                  Next <ChevronRight aria-hidden />
                </Button>
              </div>
            </nav>
          </>
        )}
      </CardContent>
    </Card>
  );
}
