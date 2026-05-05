"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, Briefcase, Users, Upload, Settings, LogOut,
} from "lucide-react";

function LogoMark() {
  return (
    <svg width="28" height="28" viewBox="0 0 28 28" fill="none" className="shrink-0">
      <defs>
        <linearGradient id="sb-logo-bg" x1="0" y1="0" x2="28" y2="28" gradientUnits="userSpaceOnUse">
          <stop stopColor="#1a3320" />
          <stop offset="1" stopColor="#0d1f11" />
        </linearGradient>
      </defs>
      <rect width="28" height="28" rx="7" fill="url(#sb-logo-bg)" />
      {/* Three ascending staggered bars */}
      <rect x="4"  y="17" width="11" height="4" rx="2" fill="white" fillOpacity="0.35" />
      <rect x="8"  y="11.5" width="11" height="4" rx="2" fill="white" fillOpacity="0.65" />
      <rect x="12" y="6"  width="11" height="4" rx="2" fill="white" fillOpacity="1" />
    </svg>
  );
}
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

const nav = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/jobs", label: "Jobs", icon: Briefcase },
  { href: "/networking", label: "Networking", icon: Users },
  { href: "/resume", label: "Resume", icon: Upload },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();

  return (
    <aside className="flex h-full w-56 flex-col border-r border-white/8 bg-zinc-950">
      {/* Logo */}
      <div className="flex items-center gap-2 px-4 py-5 border-b border-white/8">
        <LogoMark />
        <span className="text-sm font-semibold tracking-tight">ApplyNow</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 space-y-0.5 px-2 py-3">
        {nav.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
              pathname.startsWith(href)
                ? "bg-white/10 text-white"
                : "text-zinc-400 hover:bg-white/5 hover:text-zinc-200"
            )}
          >
            <Icon className="h-4 w-4 shrink-0" />
            {label}
          </Link>
        ))}
      </nav>

      {/* User */}
      <div className="border-t border-white/8 px-3 py-3">
        <div className="mb-1 px-2 py-1">
          <p className="text-xs text-zinc-400 truncate">{user?.email}</p>
        </div>
        <button
          onClick={logout}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-zinc-400 hover:bg-white/5 hover:text-zinc-200 transition-colors"
        >
          <LogOut className="h-4 w-4 shrink-0" />
          Sign out
        </button>
      </div>
    </aside>
  );
}
