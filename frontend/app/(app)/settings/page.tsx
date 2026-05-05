"use client";
import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { settingsApi, stripe as stripeApi, dashboard, Preferences, DashboardStats } from "@/lib/api";
import { X, Plus, Sparkles, CreditCard, Loader2, Wand2 } from "lucide-react";
import Link from "next/link";
import { YC_COHORTS } from "@/lib/yc-cohorts";

const FUNDING_STAGES = ["Pre-seed", "Seed", "Series A", "Series B", "Series C+", "Public"] as const;

const EMPLOYMENT_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: "full_time", label: "Full-time" },
  { value: "part_time", label: "Part-time" },
  { value: "contract", label: "Contract" },
  { value: "internship", label: "Internship" },
];

function TagInput({
  label,
  optional,
  rightAction,
  items,
  onChange,
  placeholder,
}: {
  label?: string;
  optional?: boolean;
  rightAction?: React.ReactNode;
  items: string[];
  onChange: (items: string[]) => void;
  placeholder: string;
}) {
  const [input, setInput] = useState("");

  const add = () => {
    const trimmed = input.trim();
    if (trimmed && !items.includes(trimmed)) {
      onChange([...items, trimmed]);
    }
    setInput("");
  };

  return (
    <div className="space-y-2">
      {(label || rightAction) && (
        <div className="flex items-center justify-between">
          {label && (
            <label className="text-xs font-medium text-zinc-400">
              {label}
              {optional && <span className="ml-1.5 font-normal text-zinc-600">optional</span>}
            </label>
          )}
          {rightAction && <div>{rightAction}</div>}
        </div>
      )}
      {items.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {items.map((item) => (
            <span key={item} className="flex items-center gap-1 text-xs bg-white/8 border border-white/10 text-zinc-200 px-2.5 py-1 rounded-full">
              {item}
              <button onClick={() => onChange(items.filter((i) => i !== item))}>
                <X className="h-3 w-3 text-zinc-500 hover:text-zinc-300" />
              </button>
            </span>
          ))}
        </div>
      )}
      <div className="flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), add())}
          placeholder={placeholder}
          className="flex-1 rounded-lg border border-white/8 bg-white/5 px-3 py-1.5 text-sm text-white placeholder:text-zinc-500 focus:outline-none focus:ring-1 focus:ring-white/20"
        />
        <button
          onClick={add}
          className="flex items-center gap-1 text-xs text-zinc-300 bg-white/5 hover:bg-white/10 border border-white/8 rounded-lg px-3 py-1.5 transition-colors"
        >
          <Plus className="h-3.5 w-3.5" /> Add
        </button>
      </div>
    </div>
  );
}

function Divider() {
  return <div className="border-t border-white/6" />;
}

function Toggle({ label, checked, onChange, description }: { label: string; checked: boolean; onChange: (v: boolean) => void; description?: string }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <p className="text-sm font-medium text-zinc-200">{label}</p>
        {description && <p className="text-xs text-zinc-500 mt-0.5">{description}</p>}
      </div>
      <button
        onClick={() => onChange(!checked)}
        className={`relative h-5 w-9 rounded-full transition-colors shrink-0 ${checked ? "bg-white" : "bg-white/15"}`}
      >
        <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-zinc-900 transition-transform ${checked ? "translate-x-4" : "translate-x-0.5"}`} />
      </button>
    </div>
  );
}

// ── Billing tab ──────────────────────────────────────────────────────────────

function BillingTab({ stats }: { stats: DashboardStats | undefined }) {
  const [portalLoading, setPortalLoading] = useState(false);
  const [checkoutLoading, setCheckoutLoading] = useState(false);

  const isPro = stats?.plan === "pro";

  const openPortal = async () => {
    setPortalLoading(true);
    try {
      const { url } = await stripeApi.billingPortal();
      window.location.href = url;
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Unknown error";
      toast.error(`Billing portal error: ${msg}`);
    } finally {
      setPortalLoading(false);
    }
  };

  const openCheckout = async () => {
    setCheckoutLoading(true);
    try {
      const { url } = await stripeApi.createCheckout();
      window.location.href = url;
    } catch {
      toast.error("Could not start checkout — please try again");
    } finally {
      setCheckoutLoading(false);
    }
  };

  return (
    <div className="rounded-xl border border-white/8 bg-white/3 p-6 space-y-5">
      <div>
        <h2 className="text-sm font-medium">Current plan</h2>
        <div className="mt-3 flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/8">
            <Sparkles className="h-4 w-4 text-zinc-300" />
          </div>
          <div>
            <p className="text-sm font-semibold text-zinc-100">{isPro ? "Pro" : "Free"}</p>
            <p className="text-xs text-zinc-500">
              {isPro ? "Unlimited agent runs" : "5 jobs / 3 contacts per month"}
            </p>
          </div>
        </div>
      </div>

      <Divider />

      {isPro ? (
        <div className="space-y-3">
          <p className="text-xs text-zinc-400">
            Manage your subscription, update payment method, or cancel at any time via the Stripe billing portal.
          </p>
          <button
            onClick={openPortal}
            disabled={portalLoading}
            className="flex items-center gap-2 rounded-lg bg-white/8 hover:bg-white/12 border border-white/10 px-4 py-2 text-sm font-medium text-zinc-200 transition-colors disabled:opacity-50"
          >
            {portalLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CreditCard className="h-3.5 w-3.5" />}
            Manage subscription
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-xs text-zinc-400">
            Upgrade to Pro for unlimited job scouting, networking, and application drafts.
          </p>
          <Link
            href="/pricing"
            className="inline-flex items-center gap-2 rounded-lg bg-white px-4 py-2 text-sm font-semibold text-zinc-900 hover:bg-zinc-100 transition-colors"
          >
            <Sparkles className="h-3.5 w-3.5" /> Upgrade to Pro
          </Link>
        </div>
      )}
    </div>
  );
}

// ── Main page ────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<"prefs" | "billing">("prefs");

  const { data, isLoading } = useQuery<Preferences>({ queryKey: ["settings"], queryFn: settingsApi.get });
  const { data: stats } = useQuery<DashboardStats>({ queryKey: ["dashboard-stats"], queryFn: dashboard.stats });
  const [form, setForm] = useState<Partial<Preferences>>({});
  const [dirty, setDirty] = useState(false);
  const [autocompleteLoading, setAutocompleteLoading] = useState(false);

  useEffect(() => {
    if (data) setForm(data);
  }, [data]);

  const update = (patch: Partial<Preferences>) => {
    setForm((f) => ({ ...f, ...patch }));
    setDirty(true);
  };

  const save = useMutation({
    mutationFn: () => settingsApi.update(form),
    onSuccess: () => { toast.success("Settings saved"); setDirty(false); qc.invalidateQueries({ queryKey: ["settings"] }); },
    onError: () => toast.error("Failed to save"),
  });

  const handleAutocomplete = async () => {
    const seeds = form.target_companies ?? [];
    if (seeds.length < 5) return;
    setAutocompleteLoading(true);
    try {
      const { suggestions } = await settingsApi.autocompleteCompanies(seeds);
      if (!suggestions.length) {
        toast.info("No additional companies found");
        return;
      }
      const currentLower = new Set(seeds.map((c) => c.toLowerCase().trim()));
      const merged = [...seeds, ...suggestions.filter((s) => !currentLower.has(s.toLowerCase().trim()))];
      update({ target_companies: merged });
      toast.success(`Added ${merged.length - seeds.length} companies`);
    } catch {
      toast.error("Autocomplete failed — please try again");
    } finally {
      setAutocompleteLoading(false);
    }
  };

  if (isLoading) return <div className="animate-pulse text-zinc-500 text-sm">Loading…</div>;

  const targetCompanies = form.target_companies ?? [];
  const canAutocomplete = targetCompanies.length >= 5 && targetCompanies.length < 25;

  const tabs = [
    { id: "prefs" as const, label: "Preferences" },
    { id: "billing" as const, label: "Billing" },
  ];

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-xl font-semibold">Settings</h1>
        <p className="text-sm text-zinc-400 mt-1">Configure what your agents search for</p>
      </div>

      {/* Tab strip */}
      <div className="flex gap-1 border-b border-white/8 pb-0">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
              tab === t.id
                ? "border-white text-white"
                : "border-transparent text-zinc-500 hover:text-zinc-300"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "billing" && <BillingTab stats={stats} />}

      {tab === "prefs" && (
        <>
          {/* Preferences */}
          <div className="rounded-xl border border-white/8 bg-white/3 p-6 space-y-5">

            {/* Target roles — required */}
            <TagInput
              label="Target roles"
              items={form.target_roles ?? []}
              onChange={(v) => update({ target_roles: v })}
              placeholder="e.g. Software Engineer"
            />

            <Divider />

            {/* Target companies — optional */}
            <TagInput
              label="Target companies"
              optional
              rightAction={
                <div className="flex items-center gap-2">
                  {targetCompanies.length > 0 && (
                    <button
                      onClick={() => update({ target_companies: [] })}
                      className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
                    >
                      Clear all ({targetCompanies.length})
                    </button>
                  )}
                  <button
                    onClick={handleAutocomplete}
                    disabled={!canAutocomplete || autocompleteLoading}
                    title={targetCompanies.length < 5 ? "Add at least 5 companies first" : "Fill up to 25 with similar companies"}
                    className="flex items-center gap-1 text-xs text-zinc-300 bg-white/5 hover:bg-white/10 border border-white/8 rounded-lg px-2.5 py-1 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {autocompleteLoading ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                      <Wand2 className="h-3 w-3" />
                    )}
                    Autocomplete to 25
                  </button>
                </div>
              }
              items={targetCompanies}
              onChange={(v) => update({ target_companies: v })}
              placeholder="e.g. Stripe"
            />

            {/* YC cohorts — hidden, not deleted */}
            {false && (
              <div className="space-y-2">
                <label className="text-xs font-medium text-zinc-400">Quick add — YC cohorts</label>
                <div className="flex flex-wrap gap-2">
                  {YC_COHORTS.map((cohort) => {
                    const current = form.target_companies ?? [];
                    const allAdded = cohort.companies.every((c) => current.includes(c));
                    const toggle = () => {
                      if (allAdded) {
                        update({ target_companies: current.filter((c) => !cohort.companies.includes(c)) });
                      } else {
                        update({ target_companies: [...current, ...cohort.companies.filter((c) => !current.includes(c))] });
                      }
                    };
                    return (
                      <label key={cohort.id} className="flex items-center gap-2 cursor-pointer group">
                        <div className="relative">
                          <input type="checkbox" checked={allAdded} onChange={toggle} className="sr-only" />
                          <div className={`h-4 w-4 rounded border transition-colors ${allAdded ? "bg-white border-white" : "border-white/20 bg-white/5 group-hover:border-white/40"}`}>
                            {allAdded && (
                              <svg viewBox="0 0 10 8" className="w-full h-full p-0.5" fill="none">
                                <path d="M1 4l3 3 5-6" stroke="#18181b" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                              </svg>
                            )}
                          </div>
                        </div>
                        <span className="text-xs text-zinc-300 group-hover:text-zinc-100 transition-colors">
                          {cohort.label}<span className="ml-1 text-zinc-500">({cohort.companies.length})</span>
                        </span>
                      </label>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Funding stage & Industries — hidden, not deleted */}
            {false && (
              <>
                <div className="space-y-2">
                  <label className="text-xs font-medium text-zinc-400">
                    Funding stage
                    <span className="ml-1.5 font-normal text-zinc-600">optional</span>
                  </label>
                  <div className="flex flex-wrap gap-3">
                    {FUNDING_STAGES.map((stage) => {
                      const selected = (form.company_stages ?? []).includes(stage);
                      const toggle = () => {
                        const current = form.company_stages ?? [];
                        update({ company_stages: selected ? current.filter((s) => s !== stage) : [...current, stage] });
                      };
                      return (
                        <label key={stage} className="flex items-center gap-2 cursor-pointer group">
                          <div className="relative">
                            <input type="checkbox" checked={selected} onChange={toggle} className="sr-only" />
                            <div className={`h-4 w-4 rounded border transition-colors ${selected ? "bg-white border-white" : "border-white/20 bg-white/5 group-hover:border-white/40"}`}>
                              {selected && (
                                <svg viewBox="0 0 10 8" className="w-full h-full p-0.5" fill="none">
                                  <path d="M1 4l3 3 5-6" stroke="#18181b" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                                </svg>
                              )}
                            </div>
                          </div>
                          <span className="text-xs text-zinc-300 group-hover:text-zinc-100 transition-colors">{stage}</span>
                        </label>
                      );
                    })}
                  </div>
                </div>

                <TagInput
                  label="Industries"
                  optional
                  items={form.company_industries ?? []}
                  onChange={(v) => update({ company_industries: v })}
                  placeholder="e.g. AI/ML, Fintech, Healthtech"
                />
              </>
            )}

            <Divider />

            {/* Locations — required */}
            <TagInput
              label="Locations"
              items={form.target_locations ?? []}
              onChange={(v) => update({ target_locations: v })}
              placeholder="e.g. Remote, New York"
            />

            <Divider />

            {/* Excluded companies — optional */}
            <TagInput
              label="Excluded companies"
              optional
              items={form.excluded_companies ?? []}
              onChange={(v) => update({ excluded_companies: v })}
              placeholder="Companies to skip"
            />

            <Divider />

            {/* Employment types */}
            <div className="space-y-2">
              <label className="text-xs font-medium text-zinc-400">
                Employment types
                <span className="ml-1.5 font-normal text-zinc-600">optional</span>
              </label>
              <div className="flex flex-wrap gap-3">
                {EMPLOYMENT_TYPE_OPTIONS.map(({ value, label }) => {
                  const selected = (form.employment_types ?? ["full_time"]).includes(value);
                  const toggle = () => {
                    const current = form.employment_types ?? ["full_time"];
                    const next = selected
                      ? current.filter((t) => t !== value)
                      : [...current, value];
                    update({ employment_types: next.length ? next : ["full_time"] });
                  };
                  return (
                    <label key={value} className="flex items-center gap-2 cursor-pointer group">
                      <div className="relative">
                        <input type="checkbox" checked={selected} onChange={toggle} className="sr-only" />
                        <div className={`h-4 w-4 rounded border transition-colors ${selected ? "bg-white border-white" : "border-white/20 bg-white/5 group-hover:border-white/40"}`}>
                          {selected && (
                            <svg viewBox="0 0 10 8" className="w-full h-full p-0.5" fill="none">
                              <path d="M1 4l3 3 5-6" stroke="#18181b" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                            </svg>
                          )}
                        </div>
                      </div>
                      <span className="text-xs text-zinc-300 group-hover:text-zinc-100 transition-colors">{label}</span>
                    </label>
                  );
                })}
              </div>
            </div>

            <Divider />

            {/* Salary + experience — required */}
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="text-xs font-medium text-zinc-400">Min salary ($)</label>
                <input
                  type="number"
                  value={form.min_salary ?? ""}
                  onChange={(e) => update({ min_salary: e.target.value ? Number(e.target.value) : undefined })}
                  className="w-full rounded-lg border border-white/8 bg-white/5 px-3 py-1.5 text-sm text-white focus:outline-none focus:ring-1 focus:ring-white/20"
                  placeholder="80000"
                />
              </div>
              <div className="space-y-2">
                <label className="text-xs font-medium text-zinc-400">Experience level</label>
                <select
                  value={form.experience_level ?? ""}
                  onChange={(e) => update({ experience_level: e.target.value || null })}
                  className="w-full rounded-lg border border-white/8 bg-white/5 px-3 py-1.5 text-sm text-zinc-300 focus:outline-none focus:ring-1 focus:ring-white/20"
                >
                  <option value="">Any</option>
                  {["new_grad", "entry", "junior", "mid", "senior", "staff", "lead"].map((l) => (
                    <option key={l} value={l}>{l === "new_grad" ? "New Grad" : l.charAt(0).toUpperCase() + l.slice(1)}</option>
                  ))}
                </select>
              </div>
            </div>

          </div>

          {/* Agent settings */}
          <div className="rounded-xl border border-white/8 bg-white/3 p-6 space-y-4">
            <h2 className="text-sm font-medium">Agent Settings</h2>
            <Toggle
              label="Job Scout"
              description="Searches for new jobs every 4 hours"
              checked={form.scout_enabled ?? true}
              onChange={(v) => update({ scout_enabled: v })}
            />
            <Divider />
            <Toggle
              label="Networking Agent"
              description="Finds contacts at your target companies on Wednesdays and Sundays"
              checked={form.networking_enabled ?? true}
              onChange={(v) => update({ networking_enabled: v })}
            />
          </div>

          {dirty && (
            <div className="flex items-center gap-3">
              <button
                onClick={() => save.mutate()}
                disabled={save.isPending}
                className="rounded-lg bg-white px-5 py-2 text-sm font-semibold text-zinc-900 hover:bg-zinc-100 disabled:opacity-50 transition-colors"
              >
                {save.isPending ? "Saving…" : "Save changes"}
              </button>
              <button
                onClick={() => { setForm(data ?? {}); setDirty(false); }}
                className="text-sm text-zinc-400 hover:text-zinc-200 transition-colors"
              >
                Cancel
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
