import Link from "next/link";
import { ArrowRight, Plug, Search, PenLine } from "lucide-react";
import { MarketingFooter, MarketingNav } from "@/components/marketing/Nav";
import { Button } from "@/components/ui/button";

const USE_CASES = [
  {
    title: "Business development",
    body: "Find the VP who owns the budget at every account on your list — not whoever answers the contact form.",
  },
  {
    title: "Fundraising",
    body: "Partners and principals investing at your stage, with a first message that leads on traction.",
  },
  {
    title: "Recruiting",
    body: "Engineers already doing the work you're hiring for, approached like people rather than leads.",
  },
  {
    title: "Job search",
    body: "The peers and hiring managers inside a company who will actually reply to you.",
  },
];

const STEPS = [
  {
    icon: Search,
    title: "Describe who you want to meet",
    body: "A goal in plain English, the titles that matter, and the companies or industries to look at.",
  },
  {
    icon: PenLine,
    title: "Sparrow finds them and writes",
    body: "It searches for real people at those companies, ranks them for your goal, and drafts a first message to each.",
  },
  {
    icon: Plug,
    title: "Review, send, or drive it from your AI tools",
    body: "Everything shows up in the app. Connect Sparrow over MCP and run it from Claude or Cursor instead.",
  },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-surface">
      <div className="aurora-hero absolute inset-x-0 top-0 h-[520px]" />
      <MarketingNav />

      <main className="relative z-10">
        <section className="grid-bg grid-bg-fade mx-auto max-w-5xl px-6 pb-20 pt-16 text-center">
          <div className="mx-auto inline-flex items-center gap-2 rounded-full border border-border-subtle bg-surface px-3 py-1 text-xs text-text-muted">
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-60" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-accent" />
            </span>
            Now speaks MCP
          </div>

          <h1 className="mx-auto mt-6 max-w-3xl text-4xl font-semibold tracking-tight sm:text-5xl">
            The hard part of outreach isn&apos;t sending. It&apos;s knowing who to write to.
          </h1>
          <p className="mx-auto mt-5 max-w-xl text-lg text-text-muted">
            Sparrow finds the right person at each company you care about and drafts the first
            message — for business development, fundraising, recruiting, or a job search.
          </p>

          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <Button asChild size="lg">
              <Link href="/register">
                Start with 25 free credits
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
            <Button asChild size="lg" variant="outline">
              <Link href="/pricing">See pricing</Link>
            </Button>
          </div>
          <p className="mt-3 text-xs text-text-subtle">No subscription. No card to start.</p>
        </section>

        <section className="mx-auto max-w-5xl px-6 pb-20">
          <div className="grid gap-4 sm:grid-cols-3">
            {STEPS.map(({ icon: Icon, title, body }) => (
              <div key={title} className="card-glow p-6">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent-soft">
                  <Icon className="h-4 w-4 text-accent" />
                </div>
                <h3 className="mt-4 font-medium">{title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-text-muted">{body}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="mx-auto max-w-5xl px-6 pb-20">
          <h2 className="text-center text-2xl font-semibold tracking-tight">
            One agent, four very different asks
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-center text-sm text-text-muted">
            Who counts as the right person depends entirely on why you&apos;re reaching out. A
            VP is the target in business development and the wrong door in a job search — Sparrow
            ranks accordingly.
          </p>
          <div className="mt-8 grid gap-4 sm:grid-cols-2">
            {USE_CASES.map((useCase) => (
              <div
                key={useCase.title}
                className="rounded-xl border border-border-subtle bg-surface p-6"
              >
                <h3 className="font-medium">{useCase.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-text-muted">{useCase.body}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="mx-auto max-w-5xl px-6 pb-24">
          <div className="rounded-2xl border border-border-subtle bg-surface-sunk px-6 py-12 text-center">
            <h2 className="text-2xl font-semibold tracking-tight">
              Pay for what you use, nothing else
            </h2>
            <p className="mx-auto mt-3 max-w-md text-sm text-text-muted">
              Credits, not a subscription. A contact costs one, a drafted message costs two, and
              nothing runs when your balance hits zero.
            </p>
            <Button asChild size="lg" className="mt-6">
              <Link href="/register">
                Get started free
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
          </div>
        </section>
      </main>

      <MarketingFooter />
    </div>
  );
}
