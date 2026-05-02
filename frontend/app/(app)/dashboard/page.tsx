"use client";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { dashboard, agents, DashboardStats, AgentRun } from "@/lib/api";
import { Briefcase, Users, FileText, Sparkles, Play, CheckCircle2, XCircle, Loader2, Clock, AlertTriangle } from "lucide-react";

function ScoreRing({ value, limit }: { value: number; limit: number | null }) {
  const pct = limit ? Math.min((value / limit) * 100, 100) : 0;
  const isAtLimit = limit !== null && value >= limit;
  return (
    <div className="flex items-center gap-2">
      <span className={`text-sm font-medium ${isAtLimit ? "text-amber-400" : "text-zinc-300"}`}>
        {value}{limit !== null ? ` / ${limit}` : ""}
      </span>
      {isAtLimit && (
        <span className="text-xs text-amber-400 bg-amber-400/10 px-2 py-0.5 rounded-full">Limit reached</span>
      )}
    </div>
  );
}

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

function AgentRunRow({ run }: { run: AgentRun }) {
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
        {run.status === "failed" && run.error_message && (
          <p className="text-xs text-red-400 mt-0.5 truncate" title={run.error_message}>
            {run.error_message.length > 80 ? run.error_message.slice(0, 80) + "…" : run.error_message}
          </p>
        )}
        {run.status === "completed" && (
          <p className="text-xs text-zinc-500 mt-0.5">{results || "No new results"}</p>
        )}
      </div>
      <span className="text-xs text-zinc-600 shrink-0">{when}</span>
    </div>
  );
}

export default function DashboardPage() {
  const { data: stats, isLoading } = useQuery<DashboardStats>({
    queryKey: ["dashboard-stats"],
    queryFn: dashboard.stats,
  });
  const { data: activity } = useQuery({ queryKey: ["dashboard-activity"], queryFn: dashboard.activity });
  const { data: runs } = useQuery<AgentRun[]>({
    queryKey: ["agent-runs"],
    queryFn: () => agents.runs(),
    refetchInterval: 15_000,
  });

  const runAgent = async (fn: () => Promise<unknown>, label: string) => {
    try {
      await fn();
      toast.success(`${label} started`);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "";
      if (msg.includes("402") || msg.toLowerCase().includes("limit reached")) {
        toast.error("Monthly run limit reached — upgrade to Pro for unlimited runs");
      } else {
        toast.error(`Failed to start ${label}`);
      }
    }
  };

  if (isLoading) return <div className="animate-pulse text-zinc-500 text-sm">Loading…</div>;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-xl font-semibold">Dashboard</h1>
        <p className="text-sm text-zinc-400 mt-1">Your agents are working 24/7</p>
      </div>

      {/* Setup banner — shown when target roles not yet configured */}
      {stats && !stats.target_roles_configured && (
        <div className="flex items-start gap-3 rounded-xl border border-amber-400/20 bg-amber-400/8 p-4">
          <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-amber-300">Finish setting up your profile</p>
            <p className="text-xs text-amber-400/80 mt-0.5">
              Add your target roles and companies in Settings so your agents know what to look for.
            </p>
          </div>
          <a
            href="/settings"
            className="shrink-0 text-xs font-medium text-amber-300 bg-amber-400/15 hover:bg-amber-400/25 rounded-lg px-3 py-1.5 transition-colors"
          >
            Go to Settings
          </a>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label="Jobs Found" value={stats?.jobs_count ?? 0} icon={Briefcase} sub={`${stats?.new_jobs_count ?? 0} new`} />
        <StatCard label="Drafts" value={stats?.applications_count ?? 0} icon={FileText} />
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
          <a
            href="/pricing"
            className="mt-4 inline-flex items-center gap-1.5 text-xs font-medium text-white bg-white/8 hover:bg-white/12 rounded-lg px-3 py-1.5 transition-colors"
          >
            <Sparkles className="h-3 w-3" /> Upgrade to Pro for unlimited runs
          </a>
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
            {runs.slice(0, 15).map((run) => (
              <AgentRunRow key={run.id} run={run} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
