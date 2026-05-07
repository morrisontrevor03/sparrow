"use client";
import { useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { stripe } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Check, Heart, Eye, Shield } from "lucide-react";
import { track } from "@/lib/posthog";

const FREE_FEATURES = [
  "Up to 10 contacts / month",
  "Up to 10 jobs / month",
  "3 sets of tailored materials / month",
  "Email alerts for high-match jobs",
];

const PRO_FEATURES = [
  "Unlimited Job Scout runs",
  "Unlimited Networking runs",
  "Unlimited Application drafts",
  "Email alerts for high-match jobs",
  "Priority agent processing",
];

const PROMISES = [
  {
    icon: Heart,
    title: "Relationship-first networking",
    body: "We find the right people at your target companies and draft warm, personalized outreach — not cold spam.",
  },
  {
    icon: Eye,
    title: "You review everything",
    body: "Every resume, cover letter, and message is drafted for you to read, edit, and send yourself. Nothing goes out without your approval.",
  },
  {
    icon: Shield,
    title: "No auto-applying. Ever.",
    body: "We believe applying is a human act. ApplyNow prepares you to apply faster and smarter — you pull the trigger.",
  },
];

export default function PricingPage() {
  const [loading, setLoading] = useState(false);
  const { user } = useAuth();

  const handleUpgrade = async () => {
    track("checkout_started", { source: "pricing_page" });
    if (!user) {
      window.location.href = "/register";
      return;
    }
    setLoading(true);
    try {
      const { url } = await stripe.createCheckout();
      window.location.href = url;
    } catch {
      toast.error("Failed to start checkout");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen text-zinc-50">
      {/* Nav */}
      <header className="border-b border-white/[0.06] backdrop-blur-xl backdrop-saturate-150 sticky top-0 z-40 bg-zinc-950/60">
        <div className="mx-auto max-w-5xl px-6 h-14 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 28 28" fill="none" className="h-7 w-7">
              <defs>
                <linearGradient id="pricing-bg" x1="0" y1="0" x2="28" y2="28" gradientUnits="userSpaceOnUse">
                  <stop stopColor="#1a3320"/>
                  <stop offset="1" stopColor="#0d1f11"/>
                </linearGradient>
              </defs>
              <rect width="28" height="28" rx="7" fill="url(#pricing-bg)"/>
              <rect x="4"  y="17"   width="11" height="4" rx="2" fill="white" fillOpacity="0.35"/>
              <rect x="8"  y="11.5" width="11" height="4" rx="2" fill="white" fillOpacity="0.65"/>
              <rect x="12" y="6"    width="11" height="4" rx="2" fill="white" fillOpacity="1"/>
            </svg>
            <span className="text-sm font-semibold">ApplyNow</span>
          </Link>
          <div className="flex items-center gap-3">
            <Link href="/login" className="text-sm text-zinc-400 hover:text-white transition-colors">Sign in</Link>
            <Link href="/register" className="rounded-lg bg-white px-4 py-1.5 text-sm font-semibold text-zinc-900 hover:bg-zinc-100 transition-colors">
              Get started
            </Link>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-3xl px-6 py-20">
        {/* Hero */}
        <div className="text-center mb-6">
          <h1 className="text-3xl font-bold mb-3">Simple, honest pricing</h1>
          <p className="text-zinc-400 max-w-md mx-auto">
            Start free. Upgrade when the agents prove their worth.
          </p>
        </div>

        {/* Promise banner */}
        <div className="mb-14 rounded-2xl border border-white/8 bg-white/3 px-6 py-5 text-center">
          <p className="text-sm text-zinc-300 leading-relaxed">
            <span className="font-semibold text-white">No auto-applying. You review everything.</span>
            {" "}ApplyNow is a relationship-first platform — we draft, you decide.
          </p>
        </div>

        {/* Plans */}
        <div className="grid gap-5 sm:grid-cols-2 mb-20">
          {/* Free */}
          <div className="rounded-2xl border border-white/8 bg-white/3 p-7 flex flex-col">
            <div className="mb-6">
              <p className="text-sm font-medium text-zinc-400 mb-1">Free</p>
              <p className="text-3xl font-bold">$0</p>
              <p className="text-xs text-zinc-500 mt-1">Forever</p>
            </div>
            <ul className="space-y-2.5 flex-1 mb-8">
              {FREE_FEATURES.map((f) => (
                <li key={f} className="flex items-start gap-2.5 text-sm text-zinc-300">
                  <Check className="h-4 w-4 text-zinc-400 shrink-0 mt-0.5" />
                  {f}
                </li>
              ))}
            </ul>
            <Link
              href="/register"
              onClick={() => track("signup_started", { source: "pricing_free_cta" })}
              className="block text-center rounded-xl border border-white/10 px-5 py-2.5 text-sm font-semibold text-zinc-200 hover:bg-white/5 transition-colors"
            >
              Get started free
            </Link>
          </div>

          {/* Pro */}
          <div className="rounded-2xl border border-white/20 bg-white/5 p-7 flex flex-col relative overflow-hidden">
            <div className="absolute top-4 right-4">
              <span className="text-xs font-semibold bg-white text-zinc-900 px-2.5 py-1 rounded-full">Popular</span>
            </div>
            <div className="mb-6">
              <p className="text-sm font-medium text-zinc-300 mb-1">Pro</p>
              <div className="flex items-baseline gap-1">
                <p className="text-3xl font-bold">$14.99</p>
                <p className="text-sm text-zinc-400">/ month</p>
              </div>
              <p className="text-xs text-zinc-500 mt-1">Cancel anytime</p>
            </div>
            <ul className="space-y-2.5 flex-1 mb-8">
              {PRO_FEATURES.map((f) => (
                <li key={f} className="flex items-start gap-2.5 text-sm text-zinc-200">
                  <Check className="h-4 w-4 text-white shrink-0 mt-0.5" />
                  {f}
                </li>
              ))}
            </ul>
            <button
              onClick={handleUpgrade}
              disabled={loading}
              className="rounded-xl bg-white px-5 py-2.5 text-sm font-semibold text-zinc-900 hover:bg-zinc-100 disabled:opacity-50 transition-colors"
            >
              {loading ? "Redirecting…" : "Upgrade to Pro →"}
            </button>
          </div>
        </div>

        {/* Promises */}
        <div className="space-y-4">
          <h2 className="text-center text-sm font-medium text-zinc-500 mb-6">Our commitments to you</h2>
          <div className="grid gap-4 sm:grid-cols-3">
            {PROMISES.map(({ icon: Icon, title, body }) => (
              <div key={title} className="rounded-xl border border-white/8 bg-white/3 p-5">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/8 mb-3">
                  <Icon className="h-4 w-4 text-zinc-300" />
                </div>
                <p className="text-sm font-semibold text-zinc-100 mb-1.5">{title}</p>
                <p className="text-xs text-zinc-500 leading-relaxed">{body}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
