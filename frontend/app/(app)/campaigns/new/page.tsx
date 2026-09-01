"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { TagInput } from "@/components/campaigns/TagInput";
import { campaigns, type CampaignTypeKey } from "@/lib/api";
import { cn } from "@/lib/utils";

const OBJECTIVE_PLACEHOLDER: Record<CampaignTypeKey, string> = {
  business_development:
    "Sell our observability tooling to platform engineering teams at Series B fintechs",
  job_search: "Find people on infrastructure teams who can tell me what the work is really like",
  fundraising: "Raise a $3M seed for a developer tools company with $40k MRR",
  recruiting: "Hire two senior backend engineers with distributed systems experience",
  custom: "Describe exactly what you want out of these conversations",
};

export default function NewCampaignPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const { data: types } = useQuery({ queryKey: ["campaign-types"], queryFn: campaigns.types });

  const [name, setName] = useState("");
  const [campaignType, setCampaignType] = useState<CampaignTypeKey>("business_development");
  const [objective, setObjective] = useState("");
  const [targetTitles, setTargetTitles] = useState<string[]>([]);
  const [targetCompanies, setTargetCompanies] = useState<string[]>([]);
  const [targetIndustries, setTargetIndustries] = useState<string[]>([]);
  const [targetLocations, setTargetLocations] = useState<string[]>([]);
  const [discoverBeyondList, setDiscoverBeyondList] = useState(false);

  const create = useMutation({
    mutationFn: () =>
      campaigns.create({
        name,
        campaign_type: campaignType,
        objective,
        target_titles: targetTitles,
        target_companies: targetCompanies,
        target_industries: targetIndustries,
        target_locations: targetLocations,
        discover_beyond_list: discoverBeyondList,
        status: "active",
      }),
    onSuccess: (campaign) => {
      qc.invalidateQueries({ queryKey: ["campaigns"] });
      toast.success("Campaign created");
      router.push(`/campaigns/detail?id=${campaign.id}`);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const canSubmit =
    name.trim().length > 0 &&
    targetTitles.length > 0 &&
    (targetCompanies.length > 0 || targetIndustries.length > 0);

  return (
    <div className="space-y-6">
      <div>
        <Button asChild variant="ghost" size="sm" className="-ml-2 mb-2">
          <Link href="/campaigns">
            <ArrowLeft className="h-4 w-4" />
            Campaigns
          </Link>
        </Button>
        <h1 className="text-2xl font-semibold tracking-tight">New campaign</h1>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">What kind of outreach is this?</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-2 sm:grid-cols-2">
          {(types ?? []).map((type) => (
            <button
              key={type.key}
              type="button"
              onClick={() => setCampaignType(type.key)}
              className={cn(
                "rounded-lg border p-3 text-left transition-colors",
                campaignType === type.key
                  ? "border-accent bg-accent-soft"
                  : "border-border-subtle hover:border-border-strong"
              )}
            >
              <div className="text-sm font-medium">{type.label}</div>
              <div className="mt-0.5 text-xs text-text-muted">{type.description}</div>
            </button>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">The basics</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="space-y-2">
            <Label htmlFor="name">Campaign name</Label>
            <Input
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Q3 mid-market SaaS"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="objective">What are you trying to accomplish?</Label>
            <p className="text-xs text-text-subtle">
              This goes straight into every message Sparrow drafts. The more specific, the better
              the messages.
            </p>
            <Textarea
              id="objective"
              rows={3}
              value={objective}
              onChange={(e) => setObjective(e.target.value)}
              placeholder={OBJECTIVE_PLACEHOLDER[campaignType]}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Who should Sparrow look for?</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <TagInput
            label="Job titles"
            hint="Roles to search for. Required."
            placeholder="VP of Engineering, Head of Platform"
            values={targetTitles}
            onChange={setTargetTitles}
          />
          <TagInput
            label="Target companies"
            hint="Name them directly, or leave blank and let Sparrow find them from industries."
            placeholder="Stripe, Ramp, Mercury"
            values={targetCompanies}
            onChange={setTargetCompanies}
          />
          {targetCompanies.length > 0 && (
            <div className="flex items-center justify-between gap-4 rounded-lg border border-border-subtle p-3">
              <div>
                <Label>Also discover companies beyond this list</Label>
                <p className="mt-1 text-xs text-text-muted">
                  Off by default — Sparrow will only search the companies you named above.
                </p>
              </div>
              <Switch checked={discoverBeyondList} onCheckedChange={setDiscoverBeyondList} />
            </div>
          )}
          <TagInput
            label="Industries"
            hint="Used to discover companies you didn't name."
            placeholder="fintech, developer tools"
            values={targetIndustries}
            onChange={setTargetIndustries}
          />
          <TagInput
            label="Locations"
            hint="Optional. Leave blank for anywhere."
            placeholder="New York, Remote"
            values={targetLocations}
            onChange={setTargetLocations}
          />
        </CardContent>
      </Card>

      <div className="flex items-center justify-end gap-3">
        {!canSubmit && (
          <p className="text-xs text-text-subtle">
            Add a name, at least one job title, and companies or industries.
          </p>
        )}
        <Button disabled={!canSubmit || create.isPending} onClick={() => create.mutate()}>
          {create.isPending ? "Creating…" : "Create campaign"}
        </Button>
      </div>
    </div>
  );
}
