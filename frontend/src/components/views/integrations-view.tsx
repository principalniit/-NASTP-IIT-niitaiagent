"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Plug, Plus, Trash2 } from "lucide-react";
import { useId, useState } from "react";

import { NoOrganisation } from "@/components/app/no-organisation";
import { PageHeader } from "@/components/app/page-header";
import { EmptyState, ErrorState, LoadingState } from "@/components/app/states";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { api, ApiError } from "@/lib/api";
import { useCurrentOrg } from "@/lib/current-org";
import { useEncryptionStatus, useIntegrationProviders, useIntegrations } from "@/lib/queries";
import type { Integration, IntegrationProvider, Organisation } from "@/lib/types";

const listKey = (orgId: string) => ["organisations", orgId, "integrations"];

function errorText(error: unknown, fallback: string): string {
  if (!(error instanceof ApiError)) return fallback;
  const details = error.fieldErrors().map((d) => `${(d.loc ?? []).slice(-1)[0]}: ${d.msg}`);
  return details.length ? `${error.message}. ${details.join("; ")}` : error.message;
}

function ConfigFields({
  provider,
  values,
  onChange,
}: {
  provider: IntegrationProvider;
  values: Record<string, string>;
  onChange: (values: Record<string, string>) => void;
}) {
  const base = useId();
  const required = new Set(provider.config_schema.required ?? []);
  return (
    <>
      {Object.entries(provider.config_schema.properties).map(([name, prop]) => (
        <div key={name} className="space-y-1.5">
          <Label htmlFor={`${base}-${name}`}>
            {prop.title ?? name}
            {required.has(name) ? "" : " (optional)"}
          </Label>
          <Input
            id={`${base}-${name}`}
            type={prop.type === "integer" ? "number" : "text"}
            value={values[name] ?? (prop.default !== undefined ? String(prop.default) : "")}
            placeholder={prop.description}
            onChange={(e) => onChange({ ...values, [name]: e.target.value })}
          />
        </div>
      ))}
    </>
  );
}

function toConfig(provider: IntegrationProvider, values: Record<string, string>): Record<string, unknown> {
  const config: Record<string, unknown> = {};
  for (const [name, prop] of Object.entries(provider.config_schema.properties)) {
    const raw = values[name] ?? (prop.default !== undefined ? String(prop.default) : "");
    if (raw === "") continue;
    config[name] = prop.type === "integer" ? Number(raw) : raw;
  }
  return config;
}

function AddIntegration({ org, providers, canStoreSecrets }: { org: Organisation; providers: IntegrationProvider[]; canStoreSecrets: boolean }) {
  const queryClient = useQueryClient();
  const ids = { provider: useId(), name: useId(), secret: useId() };
  const [open, setOpen] = useState(false);
  const [key, setKey] = useState(providers[0]?.key ?? "");
  const [name, setName] = useState("");
  const [values, setValues] = useState<Record<string, string>>({});
  const [secret, setSecret] = useState("");
  const provider = providers.find((p) => p.key === key);
  const create = useMutation({
    mutationFn: () =>
      api<Integration>(`/organisations/${org.id}/integrations`, {
        method: "POST",
        body: { provider: key, name: name.trim(), config: provider ? toConfig(provider, values) : {}, secret: secret || null },
      }),
    onSuccess: () => {
      setOpen(false);
      setName("");
      setValues({});
      setSecret("");
      void queryClient.invalidateQueries({ queryKey: listKey(org.id) });
    },
  });
  if (!open) {
    return <Button onClick={() => setOpen(true)}><Plus aria-hidden /> Add integration</Button>;
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>Add integration</CardTitle>
        <CardDescription>{provider?.description}</CardDescription>
      </CardHeader>
      <CardContent>
        <form
          className="grid gap-4 md:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor={ids.provider}>Service</Label>
            <NativeSelect id={ids.provider} value={key} onChange={(e) => { setKey(e.target.value); setValues({}); }}>
              {providers.map((p) => <option key={p.key} value={p.key}>{p.name}</option>)}
            </NativeSelect>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={ids.name}>Name</Label>
            <Input id={ids.name} value={name} maxLength={100} placeholder="For example: NIIT website" onChange={(e) => setName(e.target.value)} />
          </div>
          {provider ? <ConfigFields provider={provider} values={values} onChange={setValues} /> : null}
          <div className="space-y-1.5 md:col-span-2">
            <Label htmlFor={ids.secret}>{provider?.secret_label ?? "Credential"} (optional)</Label>
            <Input
              id={ids.secret}
              type="password"
              autoComplete="off"
              value={secret}
              disabled={!canStoreSecrets}
              onChange={(e) => setSecret(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              {canStoreSecrets
                ? "Encrypted before it is stored, and never shown again."
                : "Credentials cannot be stored until the server operator sets an encryption key."}
            </p>
          </div>
          {create.error ? (
            <Alert variant="destructive" className="md:col-span-2"><AlertDescription>{errorText(create.error, "Could not save the integration.")}</AlertDescription></Alert>
          ) : null}
          <div className="flex gap-2 md:col-span-2">
            <Button type="submit" disabled={create.isPending || name.trim().length < 2}>Save integration</Button>
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function IntegrationCard({ integration, provider, org, canStoreSecrets }: { integration: Integration; provider?: IntegrationProvider; org: Organisation; canStoreSecrets: boolean }) {
  const queryClient = useQueryClient();
  const secretId = useId();
  const [secret, setSecret] = useState("");
  const [confirming, setConfirming] = useState(false);
  const refresh = () => void queryClient.invalidateQueries({ queryKey: listKey(org.id) });
  const update = useMutation({
    mutationFn: (body: Record<string, unknown>) => api<Integration>(`/integrations/${integration.id}`, { method: "PATCH", body }),
    onSuccess: () => {
      setSecret("");
      refresh();
    },
  });
  const remove = useMutation({
    mutationFn: () => api(`/integrations/${integration.id}`, { method: "DELETE" }),
    onSuccess: refresh,
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2 text-base">
          <Plug className="size-4" aria-hidden /> {integration.name}
          <Badge variant="secondary">{provider?.name ?? integration.provider}</Badge>
          <Badge variant="outline">{integration.enabled ? "Enabled (recorded only)" : "Off"}</Badge>
        </CardTitle>
        <CardDescription>Not connected: the platform does not contact this service.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {Object.keys(integration.config).length ? (
          <dl className="grid gap-1 sm:grid-cols-2">
            {Object.entries(integration.config).map(([k, v]) => (
              <div key={k}>
                <dt className="text-xs text-muted-foreground">{provider?.config_schema.properties[k]?.title ?? k}</dt>
                <dd className="break-all">{String(v)}</dd>
              </div>
            ))}
          </dl>
        ) : null}
        <p className="flex items-center gap-2">
          <KeyRound className="size-4 text-muted-foreground" aria-hidden />
          {integration.secret_set ? `Credential stored (${integration.secret_hint})` : "No credential stored"}
        </p>
        <div className="flex flex-wrap items-end gap-2">
          <div className="space-y-1.5">
            <Label htmlFor={secretId}>{integration.secret_set ? "Replace credential" : "Add credential"}</Label>
            <Input id={secretId} type="password" autoComplete="off" className="w-64" value={secret} disabled={!canStoreSecrets} onChange={(e) => setSecret(e.target.value)} />
          </div>
          <Button size="sm" variant="outline" disabled={!secret || update.isPending} onClick={() => update.mutate({ secret })}>Save credential</Button>
          {integration.secret_set ? (
            <Button size="sm" variant="ghost" disabled={update.isPending} onClick={() => update.mutate({ clear_secret: true })}>Remove credential</Button>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2 border-t pt-3">
          <Button size="sm" variant="outline" disabled={update.isPending} onClick={() => update.mutate({ enabled: !integration.enabled })}>
            {integration.enabled ? "Turn off" : "Turn on"}
          </Button>
          {confirming ? (
            <>
              <Button size="sm" variant="destructive" disabled={remove.isPending} onClick={() => remove.mutate()}>Delete integration</Button>
              <Button size="sm" variant="ghost" onClick={() => setConfirming(false)}>Keep</Button>
            </>
          ) : (
            <Button size="sm" variant="ghost" onClick={() => setConfirming(true)}><Trash2 aria-hidden /> Delete</Button>
          )}
        </div>
        {update.error || remove.error ? (
          <Alert variant="destructive"><AlertDescription>{errorText(update.error ?? remove.error, "The change failed.")}</AlertDescription></Alert>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function IntegrationsView() {
  const { current, can, isLoading } = useCurrentOrg();
  const manage = can("integrations:manage");
  const providers = useIntegrationProviders();
  const integrations = useIntegrations(current?.id ?? null, manage);
  const encryption = useEncryptionStatus(current?.id ?? null, manage);
  if (isLoading) return <LoadingState />;
  if (!current) return <NoOrganisation />;
  const header = (
    <PageHeader
      title="Integrations"
      description="Connections to outside services such as Search Console, analytics, the CMS and notifications."
    />
  );
  if (!manage) {
    return (
      <>
        {header}
        <EmptyState title="Owners and administrators manage integrations" description="Integration settings include account details, so they are limited to these roles." />
      </>
    );
  }
  const canStoreSecrets = encryption.data?.available ?? false;
  return (
    <>
      {header}
      <Alert className="mb-6">
        <Plug aria-hidden />
        <AlertTitle>Records only</AlertTitle>
        <AlertDescription>
          The platform does not connect to these services yet, and never publishes to the website. Connecting any of them,
          and any paid service, needs the project owner&apos;s authorisation. Saving an integration here only records the
          settings for later.
        </AlertDescription>
      </Alert>
      {encryption.data && !canStoreSecrets ? (
        <Alert className="mb-6">
          <KeyRound aria-hidden />
          <AlertDescription>
            Credentials cannot be stored until the server operator sets <code>INTEGRATIONS_ENCRYPTION_KEYS</code>. Other
            settings can be saved now.
          </AlertDescription>
        </Alert>
      ) : null}
      {providers.isLoading || integrations.isLoading ? (
        <LoadingState rows={3} />
      ) : providers.error || integrations.error ? (
        <ErrorState error={providers.error ?? integrations.error} onRetry={() => { void providers.refetch(); void integrations.refetch(); }} />
      ) : (
        <div className="space-y-4">
          <AddIntegration org={current} providers={providers.data ?? []} canStoreSecrets={canStoreSecrets} />
          {integrations.data?.length ? (
            integrations.data.map((i) => (
              <IntegrationCard key={i.id} integration={i} provider={providers.data?.find((p) => p.key === i.provider)} org={current} canStoreSecrets={canStoreSecrets} />
            ))
          ) : (
            <EmptyState title="No integrations recorded" description="Nothing is connected. Add a record when the owner approves a service." />
          )}
        </div>
      )}
    </>
  );
}
