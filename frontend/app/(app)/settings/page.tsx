"use client";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Check, Copy, Plug, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { billing, connections, settingsApi } from "@/lib/api";

const MCP_URL = `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/mcp`;

function NotificationsTab() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["settings"], queryFn: settingsApi.get });

  const update = useMutation({
    mutationFn: settingsApi.update,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["settings"] });
      toast.success("Saved");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (!data) return <Skeleton className="h-40" />;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Email</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="flex items-center justify-between gap-4">
          <div>
            <Label>Weekly summary</Label>
            <p className="mt-1 text-xs text-text-muted">
              What Sparrow found and drafted, every Friday.
            </p>
          </div>
          <Switch
            checked={data.email_digest_enabled}
            onCheckedChange={(v) => update.mutate({ email_digest_enabled: v })}
          />
        </div>
        <div className="flex items-center justify-between gap-4">
          <div>
            <Label>Low balance alerts</Label>
            <p className="mt-1 text-xs text-text-muted">
              A heads-up before autopilot campaigns run out of credits.
            </p>
          </div>
          <Switch
            checked={data.email_low_balance_enabled}
            onCheckedChange={(v) => update.mutate({ email_low_balance_enabled: v })}
          />
        </div>
      </CardContent>
    </Card>
  );
}

function BillingTab() {
  const { data: balance } = useQuery({ queryKey: ["balance"], queryFn: billing.balance });
  const { data: packs } = useQuery({ queryKey: ["packs"], queryFn: billing.packs });
  const { data: ledger } = useQuery({ queryKey: ["ledger"], queryFn: billing.ledger });

  const checkout = useMutation({
    mutationFn: billing.checkout,
    onSuccess: (res) => {
      window.location.assign(res.url);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="flex items-end justify-between gap-4 py-6">
          <div>
            <div className="text-3xl font-semibold tabular-nums leading-none">
              {balance?.balance ?? "—"}
            </div>
            <p className="mt-2 text-sm text-text-muted">credits remaining</p>
          </div>
          {balance && (
            <p className="text-right text-xs text-text-subtle">
              {balance.costs.contact} per contact found
              <br />
              {balance.costs.draft} per message drafted
            </p>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-3 sm:grid-cols-3">
        {(packs ?? []).map((pack) => (
          <Card key={pack.id}>
            <CardContent className="space-y-3 py-5 text-center">
              <div className="text-sm font-medium">{pack.name}</div>
              <div className="text-2xl font-semibold tabular-nums">
                ${(pack.amount_cents / 100).toFixed(0)}
              </div>
              <div className="text-xs text-text-muted">
                {pack.credits.toLocaleString()} credits
              </div>
              <Button
                className="w-full"
                variant="outline"
                onClick={() => checkout.mutate(pack.id)}
                disabled={checkout.isPending}
              >
                Buy
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">History</CardTitle>
        </CardHeader>
        <CardContent className="py-0">
          {!ledger?.length ? (
            <p className="py-8 text-center text-sm text-text-muted">Nothing yet.</p>
          ) : (
            <div className="divide-y divide-border-subtle">
              {ledger.map((entry) => (
                <div key={entry.id} className="flex items-center justify-between gap-4 py-3">
                  <div>
                    <p className="text-sm capitalize">{entry.reason.replace(/_/g, " ")}</p>
                    <p className="mt-0.5 text-xs text-text-subtle">
                      {entry.created_at ? new Date(entry.created_at).toLocaleString() : "—"}
                    </p>
                  </div>
                  <span
                    className={`font-mono text-sm tabular-nums ${
                      entry.delta > 0 ? "text-accent" : "text-text-muted"
                    }`}
                  >
                    {entry.delta > 0 ? "+" : ""}
                    {entry.delta}
                  </span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function ConnectionsTab() {
  const qc = useQueryClient();
  const [copied, setCopied] = useState(false);
  const { data, isLoading } = useQuery({ queryKey: ["connections"], queryFn: connections.list });

  const revoke = useMutation({
    mutationFn: connections.revoke,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["connections"] });
      toast.success("Connection revoked");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const command = `claude mcp add --transport http sparrow ${MCP_URL}`;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Connect Sparrow to your AI tools</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-text-muted">
            Sparrow speaks MCP, so Claude, Claude Code, and Cursor can run your campaigns
            directly. Connecting opens a browser window where you choose what to grant.
          </p>
          <div className="flex items-center gap-2 rounded-lg border border-border-subtle bg-surface-sunk p-3">
            <code className="flex-1 overflow-x-auto whitespace-nowrap font-mono text-xs">
              {command}
            </code>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                navigator.clipboard.writeText(command);
                setCopied(true);
                setTimeout(() => setCopied(false), 1500);
              }}
            >
              {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
            </Button>
          </div>
          <p className="text-xs text-text-subtle">
            Tool calls that find contacts or draft messages spend credits, exactly as they do in
            the app.
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Authorized clients</CardTitle>
        </CardHeader>
        <CardContent className="py-0">
          {isLoading ? (
            <div className="py-4">
              <Skeleton className="h-16" />
            </div>
          ) : !data?.length ? (
            <div className="flex flex-col items-center gap-2 py-10 text-center">
              <Plug className="h-5 w-5 text-text-subtle" />
              <p className="text-sm text-text-muted">No clients connected yet.</p>
            </div>
          ) : (
            <div className="divide-y divide-border-subtle">
              {data.map((conn) => (
                <div key={conn.id} className="flex items-center justify-between gap-4 py-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{conn.client_name}</p>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {conn.scope.map((s) => (
                        <Badge key={s} variant="secondary" className="text-[10px]">
                          {s}
                        </Badge>
                      ))}
                    </div>
                    <p className="mt-1 text-xs text-text-subtle">
                      {conn.last_used_at
                        ? `Last used ${new Date(conn.last_used_at).toLocaleDateString()}`
                        : "Never used"}
                    </p>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => revoke.mutate(conn.id)}
                    disabled={revoke.isPending}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    Revoke
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

const TABS = ["notifications", "billing", "connections"] as const;

function SettingsTabs() {
  const params = useSearchParams();
  // Read the deep-link once at mount. Doing this in an effect would set state
  // on every render pass and fight the user's own tab clicks.
  const [tab, setTab] = useState(() => {
    const requested = params.get("tab");
    return requested && (TABS as readonly string[]).includes(requested)
      ? requested
      : "notifications";
  });

  return (
    <Tabs value={tab} onValueChange={setTab}>
      <TabsList>
        <TabsTrigger value="notifications">Notifications</TabsTrigger>
        <TabsTrigger value="billing">Billing</TabsTrigger>
        <TabsTrigger value="connections">Connections</TabsTrigger>
      </TabsList>
      <TabsContent value="notifications" className="mt-4">
        <NotificationsTab />
      </TabsContent>
      <TabsContent value="billing" className="mt-4">
        <BillingTab />
      </TabsContent>
      <TabsContent value="connections" className="mt-4">
        <ConnectionsTab />
      </TabsContent>
    </Tabs>
  );
}

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
      <Suspense fallback={<Skeleton className="h-64" />}>
        <SettingsTabs />
      </Suspense>
    </div>
  );
}
