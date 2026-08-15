"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { LayoutDashboard, Megaphone, Users, User, Settings, LogOut } from "lucide-react";
import { Wordmark } from "@/components/brand/Logo";
import { billing } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/campaigns", label: "Campaigns", icon: Megaphone },
  { href: "/contacts", label: "Contacts", icon: Users },
  { href: "/profile", label: "Profile", icon: User },
  { href: "/settings", label: "Settings", icon: Settings },
];

function CreditChip() {
  const { data } = useQuery({
    queryKey: ["balance"],
    queryFn: billing.balance,
    refetchInterval: 60_000,
  });

  if (!data) return null;

  return (
    <Link
      href="/settings?tab=billing"
      className={cn(
        "flex items-center justify-between rounded-lg border px-3 py-2 text-sm transition-colors",
        data.low_balance
          ? "border-warning/30 bg-warning-soft text-warning hover:border-warning/50"
          : "border-border-subtle bg-surface-sunk text-text-muted hover:border-border-strong"
      )}
    >
      <span>Credits</span>
      <span className="font-mono font-semibold tabular-nums">{data.balance}</span>
    </Link>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-border-subtle bg-surface">
      <div className="px-5 py-5">
        <Link href="/dashboard">
          <Wordmark />
        </Link>
      </div>

      <nav className="flex-1 space-y-0.5 px-3">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || pathname.startsWith(`${href}/`);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-surface-sunk font-medium text-text"
                  : "text-text-muted hover:bg-surface-sunk hover:text-text"
              )}
            >
              <Icon className="h-4 w-4" strokeWidth={active ? 2.2 : 1.8} />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="space-y-3 border-t border-border-subtle p-3">
        <CreditChip />
        <div className="flex items-center justify-between gap-2 px-1">
          <span className="truncate text-xs text-text-subtle" title={user?.email}>
            {user?.email}
          </span>
          <button
            onClick={logout}
            aria-label="Sign out"
            className="rounded-md p-1.5 text-text-subtle transition-colors hover:bg-surface-sunk hover:text-text"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </aside>
  );
}
