"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { ArrowRight, Check } from "lucide-react";
import { LogoMark } from "@/components/brand/Logo";
import { TagInput } from "@/components/campaigns/TagInput";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { campaigns, settingsApi, type CampaignTypeKey } from "@/lib/api";
import { track } from "@/lib/posthog";
import { cn } from "@/lib/utils";

const STEPS = ["You", "Goal", "Targets"] as const;

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState(0);

  const [headline, setHeadline] = useState("");
  const [valueProp, setValueProp] = useState("");
  const [campaignType, setCampaignType] = useState<CampaignTypeKey>("business_development");
  const [objective, setObjective] = useState("");
  const [name, setName] = useState("");
  const [titles, setTitles] = useState<string[]>([]);
  const [companies, setCompanies] = useState<string[]>([]);
  const [industries, setIndustries] = useState<string[]>([]);

  const { data: types } = useQuery({ queryKey: ["campaign-types"], queryFn: campaigns.types });

  const finish = useMutation({
    mutationFn: async () => {
      await settingsApi.update({ headline, value_prop: valueProp });
      return campaigns.create({
        name: name || "My first campaign",
        campaign_type: campaignType,
        objective,
        target_titles: titles,
        target_companies: companies,
        target_industries: industries,
        status: "active",
      });
    },
    onSuccess: (campaign) => {
      track("onboarding_completed", { campaign_type: campaignType });
      toast.success("You're set up");
      router.replace(`/campaigns/${campaign.id}`);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const canAdvance =
    step === 0
      ? headline.trim().length > 0
      : step === 1
        ? objective.trim().length > 0
        : titles.length > 0 && (companies.length > 0 || industries.length > 0);

  return (
    <div className="grid-bg min-h-screen bg-surface px-4 py-12">
      <div className="mx-auto max-w-lg space-y-6">
        <div className="flex flex-col items-center gap-3 text-center">
          <LogoMark className="h-10 w-10" />
          <h1 className="text-xl font-semibold tracking-tight">Set up Sparrow</h1>
        </div>

        <div className="flex items-center justify-center gap-2">
          {STEPS.map((label, i) => (
            <div key={label} className="flex items-center gap-2">
              <span
                className={cn(
                  "flex h-6 w-6 items-center justify-center rounded-full border text-xs",
                  i < step
                    ? "border-accent bg-accent text-accent-contrast"
                    : i === step
                      ? "border-accent text-accent"
                      : "border-border-strong text-text-subtle"
                )}
              >
                {i < step ? <Check className="h-3 w-3" strokeWidth={3} /> : i + 1}
              </span>
              <span
                className={cn("text-xs", i === step ? "text-text" : "text-text-subtle")}
              >
                {label}
              </span>
              {i < STEPS.length - 1 && <div className="h-px w-6 bg-border-subtle" />}
            </div>
          ))}
        </div>

        <Card>
          <CardContent className="space-y-5 py-6">
            {step === 0 && (
              <>
                <div className="space-y-2">
                  <Label htmlFor="headline">How would you introduce yourself?</Label>
                  <Input
                    id="headline"
                    value={headline}
                    onChange={(e) => setHeadline(e.target.value)}
                    placeholder="Co-founder at Kestrel — observability for data teams"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="value">What do you offer? (optional)</Label>
                  <Textarea
                    id="value"
                    rows={3}
                    value={valueProp}
                    onChange={(e) => setValueProp(e.target.value)}
                    placeholder="We cut alert noise by ~70% for teams running dbt and Airflow."
                  />
                </div>
              </>
            )}

            {step === 1 && (
              <>
                <div className="space-y-2">
                  <Label>What kind of outreach is this?</Label>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {(types ?? []).map((type) => (
                      <button
                        key={type.key}
                        type="button"
                        onClick={() => setCampaignType(type.key)}
                        className={cn(
                          "rounded-lg border p-3 text-left text-sm transition-colors",
                          campaignType === type.key
                            ? "border-accent bg-accent-soft"
                            : "border-border-subtle hover:border-border-strong"
                        )}
                      >
                        {type.label}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="objective">What are you trying to accomplish?</Label>
                  <Textarea
                    id="objective"
                    rows={3}
                    value={objective}
                    onChange={(e) => setObjective(e.target.value)}
                    placeholder="Sell our observability tooling to platform teams at Series B fintechs"
                  />
                </div>
              </>
            )}

            {step === 2 && (
              <>
                <div className="space-y-2">
                  <Label htmlFor="campaign-name">Campaign name</Label>
                  <Input
                    id="campaign-name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="My first campaign"
                  />
                </div>
                <TagInput
                  label="Job titles to reach"
                  placeholder="Head of Platform, VP Engineering"
                  values={titles}
                  onChange={setTitles}
                />
                <TagInput
                  label="Target companies"
                  hint="Or leave blank and add industries instead."
                  placeholder="Stripe, Ramp"
                  values={companies}
                  onChange={setCompanies}
                />
                <TagInput
                  label="Industries"
                  placeholder="fintech, developer tools"
                  values={industries}
                  onChange={setIndustries}
                />
              </>
            )}
          </CardContent>
        </Card>

        <div className="flex justify-between">
          <Button
            variant="ghost"
            onClick={() => setStep((s) => Math.max(0, s - 1))}
            disabled={step === 0}
          >
            Back
          </Button>
          {step < STEPS.length - 1 ? (
            <Button onClick={() => setStep((s) => s + 1)} disabled={!canAdvance}>
              Continue
              <ArrowRight className="h-4 w-4" />
            </Button>
          ) : (
            <Button onClick={() => finish.mutate()} disabled={!canAdvance || finish.isPending}>
              {finish.isPending ? "Setting up…" : "Finish"}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
