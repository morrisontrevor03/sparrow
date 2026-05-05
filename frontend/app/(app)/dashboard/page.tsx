"use client";
import { Suspense, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { dashboard, agents, DashboardStats, AgentRun } from "@/lib/api";
import {
  Briefcase, Users, Sparkles, Play, X,
  CheckCircle2, XCircle, Loader2, Clock, AlertTriangle,
  Upload, Building2, Zap, Circle,
} from "lucide-react";
import Link from "next/link";
import { track } from "@/lib/posthog";

// ── Sub-components ─────────────────────────────────────────────────────────

function StatCard({ label, value, icon: Icon, sub }: { label: string; value: number | string; icon: React.ElementType; sub?: string }) {
  return (
    <div className="rounded-xl border border-white/8 bg-white/3 p-5">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-medium text-zinc-400">{label}</span>
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-white/8">
          <Icon className="h-3.5 w-3.5 text-zinc-300" />
        </div>
      </div>
      <p className="text-2xl font-semibold">{value}</p>
      {sub && <p className="text-xs text-zinc-500 mt-1">{sub}</p>}
    </div>
  );
}

function RunStatusIcon({ status }: { status: string }) {
  if (status === "completed") return <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 shrink-0" />;
  if (status === "failed") return <XCircle className="h-3.5 w-3.5 text-red-400 shrink-0" />;
  return <Loader2 className="h-3.5 w-3.5 text-zinc-400 animate-spin shrink-0" />;
}

function AgentRunRow({ run, onDismiss }: { run: AgentRun; onDismiss?: (id: string) => void }) {
  const label: Record<string, string> = {
    job_scout: "Job Scout",
    networking: "Networking",
    application: "Application",
  };
  const results = [
    run.jobs_found > 0 && `${run.jobs_found} job${run.jobs_found > 1 ? "s" : ""}`,
    run.contacts_found > 0 && `${run.contacts_found} contact${run.contacts_found > 1 ? "s" : ""}`,
    run.applications_created > 0 && `${run.applications_created} draft${run.applications_created > 1 ? "s" : ""}`,
  ].filter(Boolean).join(", ");

  const duration = run.duration_ms ? `${(run.duration_ms / 1000).toFixed(1)}s` : null;
  const when = run.started_at
    ? new Date(run.started_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
    : null;

  return (
    <div className="flex items-start gap-3 py-2.5 border-b border-white/5 last:border-0">
      <RunStatusIcon status={run.status} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm text-zinc-200">{label[run.agent_type] ?? run.agent_type}</span>
          <span className="text-xs text-zinc-600">{run.trigger}</span>
          {duration && <span className="text-xs text-zinc-600 flex items-center gap-0.5"><Clock className="h-2.5 w-2.5" />{duration}</span>}
        </div>
        {run.status === "running" && run.current_step && (
          <p className="text-xs text-zinc-400 mt-0.5 animate-pulse">{run.current_step}</p>
        )}
        {run.status === "failed" && run.error_message && (
          <p className="text-xs text-red-400 mt-0.5 truncate" title={run.error_message}>
            {run.error_message.length > 80 ? run.error_message.slice(0, 80) + "…" : run.error_message}
          </p>
        )}
        {run.status === "completed" && (
          <p className="text-xs text-zinc-500 mt-0.5">
            {results || (
              <Link href="/settings" className="underline underline-offset-2 hover:text-zinc-400">
                No new results. Adjust Settings
              </Link>
            )}
          </p>
        )}
      </div>
      <div className="flex items-center gap-1 shrink-0">
        <span className="text-xs text-zinc-600">{when}</span>
        {run.status === "running" && onDismiss && (
          <button
            onClick={() => onDismiss(run.id)}
            className="p-1 text-zinc-700 hover:text-zinc-400 transition-colors"
            title="Dismiss"
          >
            <X className="h-3 w-3" />
          </button>
        )}
      </div>
    </div>
  );
}

// ── Start Here Checklist ───────────────────────────────────────────────────

function ChecklistItem({
  done,
  label,
  description,
  href,
  icon: Icon,
}: {
  done: boolean;
  label: string;
  description: string;
  href: string;
  icon: React.ElementType;
}) {
  return (
    <div className={`flex items-start gap-3 py-3 ${done ? "opacity-50" : ""}`}>
      <div className="mt-0.5">
        {done ? (
          <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
        ) : (
          <Circle className="h-4 w-4 text-zinc-600 shrink-0" />
        )}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className={`text-sm font-medium ${done ? "line-through text-zinc-500" : "text-zinc-200"}`}>
            {label}
          </p>
        </div>
        {!done && <p className="text-xs text-zinc-500 mt-0.5">{description}</p>}
      </div>
      {!done && (
        <Link
          href={href}
          className="shrink-0 flex items-center gap-1.5 text-xs font-medium text-zinc-300 bg-white/6 hover:bg-white/10 rounded-lg px-3 py-1.5 transition-colors"
        >
          <Icon className="h-3 w-3" />
          Go
        </Link>
      )}
    </div>
  );
}

function StartHereChecklist({ stats }: { stats: DashboardStats }) {
  const items = [
    {
      done: stats.resume_uploaded,
      label: "Upload your resume",
      description: "Parses and tailors it for every application automatically",
      href: "/resume",
      icon: Upload,
    },
    {
      done: stats.target_roles_configured,
      label: "Set target roles + location",
      description: "Tell Job Scout what to look for",
      href: "/settings",
      icon: Briefcase,
    },
    {
      done: stats.companies_configured,
      label: "Add target companies or type",
      description: "5–10 specific companies or a company type for best networking results",
      href: "/settings",
      icon: Building2,
    },
    {
      done: stats.first_run_completed,
      label: "Generate your first leads",
      description: "Run Job Scout + Networking Agent to see your first matches",
      href: "/dashboard",
      icon: Zap,
    },
  ];

  const completedCount = items.filter((i) => i.done).length;
  if (completedCount === items.length) return null;

  return (
    <div className="rounded-xl border border-white/8 bg-white/3 p-5">
      <div className="flex items-center justify-between mb-1">
        <h2 className="text-sm font-medium">Start here</h2>
        <span className="text-xs text-zinc-500">{completedCount}/{items.length} done</span>
      </div>
      <p className="text-xs text-zinc-500 mb-4">Complete setup to unlock the full agent experience.</p>
      <div className="divide-y divide-white/5">
        {items.map((item) => (
          <ChecklistItem key={item.label} {...item} />
        ))}
      </div>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────

function DashboardContent() {
  const searchParams = useSearchParams();
  const isFirstRun = searchParams.get("first_run") === "true";
  const [firstRunBannerDismissed, setFirstRunBannerDismissed] = useState(false);
  const [dismissedRunIds, setDismissedRunIds] = useState<Set<string>>(new Set());
  const dismissRun = (id: string) => setDismissedRunIds((prev) => new Set([...prev, id]));

  const { data: stats, isLoading } = useQuery<DashboardStats>({
    queryKey: ["dashboard-stats"],
    queryFn: dashboard.stats,
  });
  const { data: runs, refetch: refetchRuns } = useQuery<AgentRun[]>({
    queryKey: ["agent-runs"],
    queryFn: () => agents.runs(),
    refetchInterval: (query) =>
      query.state.data?.some((r: AgentRun) => r.status === "running") ? 3_000 : 30_000,
  });

  useEffect(() => {
    if (isFirstRun) track("first_run_dashboard_viewed");
  }, [isFirstRun]);

  const runAgent = async (fn: () => Promise<unknown>, label: string) => {
    try {
      await fn();
      toast.success(`${label} started`);
      refetchRuns();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "";
      if (msg.includes("402") || msg.toLowerCase().includes("limit reached")) {
        toast.error("Monthly run limit reached. Upgrade to Pro for unlimited runs");
        track("paywall_viewed", { source: "agent_run_limit" });
      } else {
        toast.error(`Failed to start ${label}`);
      }
    }
  };

  if (isLoading) return <div className="animate-pulse text-zinc-500 text-sm">Loading…</div>;

  const activeRuns = runs?.filter((r) => r.status === "running" || r.status === "queued") ?? [];

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-xl font-semibold">Dashboard</h1>
        <p className="text-sm text-zinc-400 mt-1">Your agents are working 24/7</p>
      </div>

      {/* First-run in-progress banner */}
      {isFirstRun && !firstRunBannerDismissed && (
        <div className="flex items-start gap-3 rounded-xl border border-white/10 bg-white/3 p-4">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white/8">
            <Zap className="h-4 w-4 text-white" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-zinc-200">
              {activeRuns.length > 0 ? "Agents are running…" : "First run complete!"}
            </p>
            <p className="text-xs text-zinc-400 mt-0.5">
              {activeRuns.length > 0
                ? "Job Scout and Networking Agent are finding your first matches. Results appear below as they come in."
                : "Scroll down to see your jobs and contacts. Your agents will keep running automatically."}
            </p>
          </div>
          <button
            onClick={() => setFirstRunBannerDismissed(true)}
            className="text-xs text-zinc-600 hover:text-zinc-400 transition-colors"
          >
            ✕
          </button>
        </div>
      )}

      {/* Setup banner — only if roles not configured and no checklist visible */}
      {stats && !stats.target_roles_configured && !isFirstRun && (
        <div className="flex items-start gap-3 rounded-xl border border-amber-400/20 bg-amber-400/8 p-4">
          <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-amber-300">Finish setting up your profile</p>
            <p className="text-xs text-amber-400/80 mt-0.5">
              Add your target roles and companies so your agents know what to look for.
            </p>
          </div>
          <Link
            href="/settings"
            className="shrink-0 text-xs font-medium text-amber-300 bg-amber-400/15 hover:bg-amber-400/25 rounded-lg px-3 py-1.5 transition-colors"
          >
            Go to Settings
          </Link>
        </div>
      )}

      {/* Start here checklist */}
      {stats && <StartHereChecklist stats={stats} />}

      {/* Stats */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <StatCard label="Jobs Found" value={stats?.jobs_count ?? 0} icon={Briefcase} sub={`${stats?.new_jobs_count ?? 0} new`} />
        <StatCard label="Contacts" value={stats?.contacts_count ?? 0} icon={Users} />
        <StatCard label="Plan" value={stats?.plan === "pro" ? "Pro" : "Free"} icon={Sparkles} />
      </div>

      {/* Usage */}
      {stats?.plan === "free" && (
        <div className="rounded-xl border border-white/8 bg-white/3 p-5">
          <h2 className="text-sm font-medium mb-4">Monthly Agent Runs</h2>
          <div className="grid grid-cols-3 gap-4">
            {[
              { label: "Job Scout", key: "job_scout" as const },
              { label: "Networking", key: "networking" as const },
              { label: "App Drafts", key: "application" as const },
            ].map(({ label, key }) => {
              const used = stats.usage.agent_runs[key];
              const limit = stats.usage.agent_runs_limit ?? 3;
              const atLimit = used >= limit;
              return (
                <div key={key}>
                  <p className="text-xs text-zinc-400 mb-1">{label}</p>
                  <div className="flex items-center gap-2">
                    <span className={`text-sm font-medium ${atLimit ? "text-amber-400" : "text-zinc-300"}`}>
                      {used} / {limit}
                    </span>
                    {atLimit && (
                      <span className="text-xs text-amber-400 bg-amber-400/10 px-1.5 py-0.5 rounded-full">Limit</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
          <Link
            href="/pricing"
            onClick={() => track("paywall_viewed", { source: "dashboard_usage_bar" })}
            className="mt-4 inline-flex items-center gap-1.5 text-xs font-medium text-white bg-white/8 hover:bg-white/12 rounded-lg px-3 py-1.5 transition-colors"
          >
            <Sparkles className="h-3 w-3" /> Upgrade to Pro for unlimited runs
          </Link>
        </div>
      )}

      {/* Manual agent triggers */}
      <div className="rounded-xl border border-white/8 bg-white/3 p-5">
        <h2 className="text-sm font-medium mb-4">Run Agents Now</h2>
        <div className="flex flex-wrap gap-2">
          {[
            { label: "Job Scout", fn: agents.runJobScout },
            { label: "Networking", fn: agents.runNetworking },
          ].map(({ label, fn }) => (
            <button
              key={label}
              onClick={() => runAgent(fn, label)}
              className="flex items-center gap-1.5 rounded-lg border border-white/8 bg-white/5 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:bg-white/10 hover:text-white transition-colors"
            >
              <Play className="h-3 w-3" /> {label}
            </button>
          ))}
        </div>
      </div>

      {/* Agent runs */}
      <div className="rounded-xl border border-white/8 bg-white/3 p-5">
        <h2 className="text-sm font-medium mb-4">Agent Runs</h2>
        {!runs || runs.length === 0 ? (
          <p className="text-sm text-zinc-500">No runs yet. Click a button above to trigger an agent manually.</p>
        ) : (
          <div>
            {runs.filter((r) => !dismissedRunIds.has(r.id)).slice(0, 15).map((run) => (
              <AgentRunRow key={run.id} run={run} onDismiss={dismissRun} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function DashboardPage() {
  return (
    <Suspense fallback={<div className="animate-pulse text-zinc-500 text-sm">Loading…</div>}>
      <DashboardContent />
    </Suspense>
  );
}
