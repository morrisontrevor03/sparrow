"use client";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Check, Users, Send, Megaphone, Coins } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { dashboard, type DashboardStats } from "@/lib/api";
import { cn } from "@/lib/utils";

function Stat({
  icon: Icon,
  value,
  label,
}: {
  icon: React.ElementType;
  value: number;
  label: string;
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 py-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-surface-sunk">
          <Icon className="h-4 w-4 text-text-muted" />
        </div>
        <div>
          <div className="text-2xl font-semibold tabular-nums leading-none">{value}</div>
          <div className="mt-1 text-xs text-text-muted">{label}</div>
        </div>
      </CardContent>
    </Card>
  );
}

const STEPS: Array<{
  key: keyof DashboardStats["setup"];
  label: string;
  href: string;
  cta: string;
}> = [
  { key: "profile_completed", label: "Tell Sparrow who you are", href: "/profile", cta: "Add your background" },
  { key: "campaign_created", label: "Create a campaign", href: "/campaigns", cta: "New campaign" },
  { key: "first_run_completed", label: "Run it and review the contacts", href: "/campaigns", cta: "Run a campaign" },
];

function StartHere({ setup }: { setup: DashboardStats["setup"] }) {
  const remaining = STEPS.filter((s) => !setup[s.key]);
  if (remaining.length === 0) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Start here</CardTitle>
      </CardHeader>
      <CardContent className="space-y-1">
        {STEPS.map((step) => {
          const done = setup[step.key];
          return (
            <div
              key={step.key}
              className="flex items-center justify-between gap-3 rounded-lg px-2 py-2"
            >
              <div className="flex items-center gap-3">
                <span
                  className={cn(
                    "flex h-5 w-5 items-center justify-center rounded-full border text-[10px]",
                    done
                      ? "border-accent bg-accent text-accent-contrast"
                      : "border-border-strong text-text-subtle"
                  )}
                >
                  {done && <Check className="h-3 w-3" strokeWidth={3} />}
                </span>
                <span className={cn("text-sm", done ? "text-text-subtle line-through" : "text-text")}>
                  {step.label}
                </span>
              </div>
              {!done && (
                <Button asChild variant="ghost" size="sm">
                  <Link href={step.href}>
                    {step.cta}
                    <ArrowRight className="h-3.5 w-3.5" />
                  </Link>
                </Button>
              )}
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}

export default function DashboardPage() {
  const { data: stats, isLoading } = useQuery({
    queryKey: ["dashboard-stats"],
    queryFn: dashboard.stats,
  });
  const { data: activity } = useQuery({
    queryKey: ["dashboard-activity"],
    queryFn: dashboard.activity,
  });

  if (isLoading || !stats) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-9 w-40" />
        <div className="grid gap-3 sm:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-[86px]" />
          ))}
        </div>
        <Skeleton className="h-48" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          <p className="mt-1 text-sm text-text-muted">
            {stats.credits.balance} credits · {stats.credits.spent_this_week} spent this week
          </p>
        </div>
        <Button asChild>
          <Link href="/campaigns">
            <Megaphone className="h-4 w-4" />
            Campaigns
          </Link>
        </Button>
      </div>

      {stats.credits.low_balance && (
        <Card className="border-warning/30 bg-warning-soft">
          <CardContent className="flex items-center justify-between gap-4 py-4">
            <div className="flex items-center gap-3">
              <Coins className="h-4 w-4 text-warning" />
              <p className="text-sm text-text">
                You&apos;re low on credits. Autopilot campaigns pause at zero — they never
                overdraft.
              </p>
            </div>
            <Button asChild size="sm" variant="outline">
              <Link href="/settings?tab=billing">Top up</Link>
            </Button>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat icon={Users} value={stats.contacts_count} label="contacts found" />
        <Stat icon={Send} value={stats.drafted_count} label="messages drafted" />
        <Stat icon={ArrowRight} value={stats.in_flight_count} label="conversations open" />
        <Stat icon={Megaphone} value={stats.active_campaign_count} label="active campaigns" />
      </div>

      <StartHere setup={stats.setup} />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent runs</CardTitle>
        </CardHeader>
        <CardContent>
          {!activity?.length ? (
            <p className="py-6 text-center text-sm text-text-muted">
              No runs yet. Create a campaign and run it to see activity here.
            </p>
          ) : (
            <div className="divide-y divide-border-subtle">
              {activity.map((run) => (
                <div key={run.id} className="flex items-center justify-between gap-4 py-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm">{run.summary ?? "Run completed"}</p>
                    <p className="mt-0.5 text-xs text-text-subtle">
                      {run.trigger === "scheduled"
                        ? "Autopilot"
                        : run.trigger === "mcp"
                          ? "Via MCP"
                          : "Manual"}{" "}
                      ·{" "}
                      {run.timestamp
                        ? new Date(run.timestamp).toLocaleDateString(undefined, {
                            month: "short",
                            day: "numeric",
                          })
                        : "—"}
                    </p>
                  </div>
                  <span className="shrink-0 font-mono text-xs text-text-subtle tabular-nums">
                    −{run.credits_spent}
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
