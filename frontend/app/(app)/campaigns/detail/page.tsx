"use client";
import { Suspense, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ArrowLeft, Play, Zap } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ContactTable } from "@/components/contacts/ContactTable";
import { campaigns } from "@/lib/api";

function CampaignDetail({ id }: { id: string }) {
  const qc = useQueryClient();
  const [running, setRunning] = useState(false);

  const { data: campaign, isLoading } = useQuery({
    queryKey: ["campaign", id],
    queryFn: () => campaigns.get(id),
  });
  const { data: contacts } = useQuery({
    queryKey: ["campaign-contacts", id],
    queryFn: () => campaigns.contacts(id),
  });
  const { data: runs } = useQuery({
    queryKey: ["campaign-runs", id],
    queryFn: () => campaigns.runs(id),
    // While a run is in flight the backend updates current_step; poll so the
    // user sees progress instead of a frozen button.
    refetchInterval: running ? 3000 : false,
  });

  const update = useMutation({
    mutationFn: (data: Parameters<typeof campaigns.update>[1]) => campaigns.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["campaign", id] }),
    onError: (e: Error) => toast.error(e.message),
  });

  const run = useMutation({
    mutationFn: () => campaigns.run(id),
    onSuccess: (res) => {
      setRunning(true);
      toast.success("Run started", { description: `${res.balance} credits available` });
      setTimeout(() => {
        setRunning(false);
        qc.invalidateQueries({ queryKey: ["campaign-contacts", id] });
        qc.invalidateQueries({ queryKey: ["balance"] });
      }, 45_000);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (isLoading || !campaign) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-9 w-56" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  const activeRun = runs?.find((r) => r.status === "running" || r.status === "queued");

  return (
    <div className="space-y-6">
      <div>
        <Button asChild variant="ghost" size="sm" className="-ml-2 mb-2">
          <Link href="/campaigns">
            <ArrowLeft className="h-4 w-4" />
            Campaigns
          </Link>
        </Button>
        <div className="flex items-end justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h1 className="truncate text-2xl font-semibold tracking-tight">{campaign.name}</h1>
              <Badge variant={campaign.status === "active" ? "default" : "secondary"}>
                {campaign.status}
              </Badge>
            </div>
            {campaign.objective && (
              <p className="mt-1 max-w-2xl text-sm text-text-muted">{campaign.objective}</p>
            )}
          </div>
          <Button onClick={() => run.mutate()} disabled={run.isPending || !!activeRun}>
            <Play className="h-4 w-4" />
            {activeRun ? "Running…" : "Run now"}
          </Button>
        </div>
      </div>

      {activeRun?.current_step && (
        <Card className="border-accent/30 bg-accent-soft">
          <CardContent className="flex items-center gap-3 py-3">
            <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-accent/30 border-t-accent" />
            <p className="text-sm">{activeRun.current_step}</p>
          </CardContent>
        </Card>
      )}

      <Tabs defaultValue="contacts">
        <TabsList>
          <TabsTrigger value="contacts">Contacts ({contacts?.length ?? 0})</TabsTrigger>
          <TabsTrigger value="targeting">Targeting</TabsTrigger>
          <TabsTrigger value="autopilot">Autopilot</TabsTrigger>
          <TabsTrigger value="runs">Runs</TabsTrigger>
        </TabsList>

        <TabsContent value="contacts" className="mt-4">
          <ContactTable
            contacts={contacts ?? []}
            emptyMessage="No contacts yet. Run the campaign to find people."
          />
        </TabsContent>

        <TabsContent value="targeting" className="mt-4">
          <Card>
            <CardContent className="space-y-4 py-5 text-sm">
              {[
                ["Job titles", campaign.target_titles],
                ["Companies", campaign.target_companies],
                ["Industries", campaign.target_industries],
                ["Locations", campaign.target_locations],
                ["Excluded", campaign.excluded_companies],
              ].map(([label, values]) => (
                <div key={label as string} className="flex gap-4">
                  <span className="w-28 shrink-0 text-text-muted">{label as string}</span>
                  <span className="text-text">
                    {(values as string[]).length ? (values as string[]).join(", ") : "—"}
                  </span>
                </div>
              ))}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="autopilot" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Zap className="h-4 w-4 text-accent" />
                Autopilot
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <Label>Run this campaign automatically</Label>
                  <p className="mt-1 text-xs text-text-muted">
                    Scheduled runs spend credits. They stop at zero balance and never overdraft.
                  </p>
                </div>
                <Switch
                  checked={campaign.autopilot_enabled}
                  onCheckedChange={(checked) => update.mutate({ autopilot_enabled: checked })}
                />
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="cadence">Every N days</Label>
                  <Input
                    id="cadence"
                    type="number"
                    min={1}
                    max={30}
                    defaultValue={campaign.autopilot_cadence_days}
                    onBlur={(e) =>
                      update.mutate({ autopilot_cadence_days: Number(e.target.value) })
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="cap">Weekly credit cap</Label>
                  <Input
                    id="cap"
                    type="number"
                    min={0}
                    defaultValue={campaign.weekly_credit_cap}
                    onBlur={(e) => update.mutate({ weekly_credit_cap: Number(e.target.value) })}
                  />
                  <p className="text-xs text-text-subtle">
                    {campaign.credits_spent_this_week} of {campaign.weekly_credit_cap} used this
                    week. Applies to scheduled runs only — manual runs are never capped.
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="runs" className="mt-4">
          <Card>
            <CardContent className="py-2">
              {!runs?.length ? (
                <p className="py-8 text-center text-sm text-text-muted">No runs yet.</p>
              ) : (
                <div className="divide-y divide-border-subtle">
                  {runs.map((r) => (
                    <div key={r.id} className="flex items-center justify-between gap-4 py-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm">
                          {r.output_summary ?? r.error_message ?? r.status}
                        </p>
                        <p className="mt-0.5 text-xs text-text-subtle">
                          {r.trigger} ·{" "}
                          {r.started_at ? new Date(r.started_at).toLocaleString() : "—"}
                        </p>
                      </div>
                      <div className="shrink-0 text-right text-xs text-text-subtle">
                        <div>
                          {r.contacts_found} found · {r.drafts_written} drafted
                        </div>
                        <div className="font-mono tabular-nums">−{r.credits_spent} credits</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

function CampaignDetailFromQuery() {
  const searchParams = useSearchParams();
  return <CampaignDetail id={searchParams.get("id") ?? ""} />;
}

export default function CampaignDetailPage() {
  return (
    <Suspense fallback={<Skeleton className="h-64" />}>
      <CampaignDetailFromQuery />
    </Suspense>
  );
}
