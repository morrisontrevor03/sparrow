import Link from "next/link";
import { BriefcaseBusiness, Users, FileCheck } from "lucide-react";

function LogoMark() {
  return (
    <svg width="28" height="28" viewBox="0 0 28 28" fill="none" className="shrink-0">
      <defs>
        <linearGradient id="mkt-logo-bg" x1="0" y1="0" x2="28" y2="28" gradientUnits="userSpaceOnUse">
          <stop stopColor="#1a3320" />
          <stop offset="1" stopColor="#0d1f11" />
        </linearGradient>
      </defs>
      <rect width="28" height="28" rx="7" fill="url(#mkt-logo-bg)" />
      {/* Three ascending staggered bars */}
      <rect x="4"  y="17" width="11" height="4" rx="2" fill="white" fillOpacity="0.35" />
      <rect x="8"  y="11.5" width="11" height="4" rx="2" fill="white" fillOpacity="0.65" />
      <rect x="12" y="6"  width="11" height="4" rx="2" fill="white" fillOpacity="1" />
    </svg>
  );
}

const features = [
  {
    icon: BriefcaseBusiness,
    title: "Job Scout",
    description:
      "AI agents scan thousands of job boards around the clock and alert you the moment a high-match posting appears, before most candidates even see it.",
  },
  {
    icon: Users,
    title: "Strategic Networking",
    description:
      "Automatically finds the right people at your target companies, hiring managers, staff engineers, and recruiters, then drafts a personalized coffee chat message for each one.",
  },
  {
    icon: FileCheck,
    title: "Instant Application Drafts",
    description:
      "For every strong match, your resume and cover letter are automatically tailored to the role. You get a polished draft in your inbox within minutes of the posting going live.",
  },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen text-zinc-50">
      {/* Nav */}
      <header className="border-b border-white/[0.06] backdrop-blur-xl backdrop-saturate-150 sticky top-0 z-40 bg-zinc-950/60">
        <div className="mx-auto max-w-5xl px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <LogoMark />
            <span className="text-sm font-semibold">ApplyNow</span>
          </div>
          <div className="flex items-center gap-3">
            <Link href="/login" className="text-sm text-zinc-400 hover:text-white transition-colors">
              Sign in
            </Link>
            <Link
              href="/register"
              className="rounded-lg bg-white px-4 py-1.5 text-sm font-semibold text-zinc-900 hover:bg-zinc-100 transition-colors"
            >
              Get started
            </Link>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 aurora-hero pointer-events-none" />
        <div className="absolute inset-0 grid-bg grid-bg-fade pointer-events-none" />
        <div className="relative mx-auto max-w-3xl px-6 py-28 text-center">
          <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-1.5 text-xs font-medium text-zinc-300 mb-8">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-signal opacity-60" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-signal" />
            </span>
            AI agents working for you 24/7
          </div>
          <h1 className="text-5xl sm:text-7xl font-semibold tracking-[-0.04em] leading-[0.95] mb-6">
            The job search agent
            <br />
            <span className="text-zinc-500">that never sleeps</span>
          </h1>
          <p className="text-lg text-zinc-400 leading-relaxed mb-10 max-w-xl mx-auto">
            ApplyNow runs AI agents around the clock to find jobs, build your network,
            and draft tailored applications so you respond before anyone else.
          </p>
          <div className="flex items-center justify-center gap-3">
            <Link
              href="/register"
              className="btn-primary rounded-xl px-6 py-3 text-sm font-semibold"
            >
              Start free
            </Link>
            <Link
              href="/pricing"
              className="rounded-xl border border-white/10 px-6 py-3 text-sm font-medium text-zinc-300 hover:bg-white/5 transition-colors"
            >
              View pricing
            </Link>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="mx-auto max-w-5xl px-6 py-20">
        <div className="grid gap-5 sm:grid-cols-3">
          {features.map(({ icon: Icon, title, description }) => (
            <div key={title} className="card-glow p-6 space-y-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 bg-white/5">
                <Icon className="h-5 w-5 text-zinc-300" />
              </div>
              <h3 className="font-semibold text-zinc-100">{title}</h3>
              <p className="text-sm text-zinc-400 leading-relaxed">{description}</p>
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="mx-auto max-w-5xl px-6 pb-24">
        <div className="relative overflow-hidden rounded-2xl border border-white/8 bg-white/3 p-10 text-center grid-bg">
          <h2 className="text-2xl font-bold mb-3">Ready to get ahead?</h2>
          <p className="text-zinc-400 text-sm mb-6">Start free. No credit card required.</p>
          <Link
            href="/register"
            className="btn-primary inline-flex rounded-xl px-6 py-2.5 text-sm font-semibold"
          >
            Create your account →
          </Link>
        </div>
      </section>

      <footer className="border-t border-white/6 py-6 text-center text-xs text-zinc-600">
        © {new Date().getFullYear()} ApplyNow · apply-now-ai.com
      </footer>
    </div>
  );
}
