"use client";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Plus, Megaphone, Zap } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { campaigns, type Campaign } from "@/lib/api";

const TYPE_LABEL: Record<Campaign["campaign_type"], string> = {
  business_development: "Business development",
  job_search: "Job search",
  fundraising: "Fundraising",
  recruiting: "Recruiting",
  custom: "Custom",
};

const STATUS_VARIANT: Record<Campaign["status"], "default" | "secondary" | "outline"> = {
  active: "default",
  paused: "secondary",
  draft: "outline",
};

function CampaignRow({ campaign }: { campaign: Campaign }) {
  return (
    <Link href={`/campaigns/${campaign.id}`} className="block">
      <Card className="transition-colors hover:border-border-strong">
        <CardContent className="flex items-center justify-between gap-4 py-4">
          <div className="min-w-0 space-y-1">
            <div className="flex items-center gap-2">
              <span className="truncate font-medium">{campaign.name}</span>
              <Badge variant={STATUS_VARIANT[campaign.status]}>{campaign.status}</Badge>
              {campaign.autopilot_enabled && (
                <span
                  className="flex items-center gap-1 text-xs text-accent"
                  title={`Autopilot every ${campaign.autopilot_cadence_days} days, capped at ${campaign.weekly_credit_cap} credits/week`}
                >
                  <Zap className="h-3 w-3" />
                  Autopilot
                </span>
              )}
            </div>
            <p className="truncate text-sm text-text-muted">
              {TYPE_LABEL[campaign.campaign_type]}
              {campaign.objective ? ` · ${campaign.objective}` : ""}
            </p>
          </div>
          <div className="shrink-0 text-right">
            <div className="text-lg font-semibold tabular-nums leading-none">
              {campaign.contact_count}
            </div>
            <div className="mt-1 text-xs text-text-subtle">contacts</div>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

export default function CampaignsPage() {
  const { data, isLoading } = useQuery({ queryKey: ["campaigns"], queryFn: campaigns.list });

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Campaigns</h1>
          <p className="mt-1 text-sm text-text-muted">
            Each campaign describes who you want to reach and why.
          </p>
        </div>
        <Button asChild>
          <Link href="/campaigns/new">
            <Plus className="h-4 w-4" />
            New campaign
          </Link>
        </Button>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-[86px]" />
          ))}
        </div>
      ) : !data?.length ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-4 py-14 text-center">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-surface-sunk">
              <Megaphone className="h-5 w-5 text-text-subtle" />
            </div>
            <div className="space-y-1">
              <p className="font-medium">No campaigns yet</p>
              <p className="mx-auto max-w-sm text-sm text-text-muted">
                A campaign is a goal plus a target list. Sparrow finds the people who match and
                writes the first message.
              </p>
            </div>
            <Button asChild>
              <Link href="/campaigns/new">Create your first campaign</Link>
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {data.map((campaign) => (
            <CampaignRow key={campaign.id} campaign={campaign} />
          ))}
        </div>
      )}
    </div>
  );
}
