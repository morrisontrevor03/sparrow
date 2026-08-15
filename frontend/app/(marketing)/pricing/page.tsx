"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { Check } from "lucide-react";
import { MarketingFooter, MarketingNav } from "@/components/marketing/Nav";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { billing } from "@/lib/api";
import { track } from "@/lib/posthog";
import { cn } from "@/lib/utils";

const PROMISES = [
  "Credits never expire.",
  "Nothing is sent on your behalf — you review and send every message yourself.",
  "Autopilot stops at a zero balance. There is no overdraft and no surprise invoice.",
  "Cancel by simply not buying more.",
];

export default function PricingPage() {
  const router = useRouter();
  const { data: packs } = useQuery({ queryKey: ["packs"], queryFn: billing.packs });

  const buy = async (packId: string) => {
    const token = typeof window !== "undefined" ? localStorage.getItem("token") : null;
    if (!token) {
      router.push("/register");
      return;
    }
    try {
      track("checkout_started", { pack_id: packId });
      const { url } = await billing.checkout(packId);
      window.location.assign(url);
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <div className="min-h-screen bg-surface">
      <div className="aurora-hero absolute inset-x-0 top-0 h-[380px]" />
      <MarketingNav />

      <main className="relative z-10 mx-auto max-w-5xl px-6 pb-24 pt-12">
        <div className="text-center">
          <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
            Pay for what you use
          </h1>
          <p className="mx-auto mt-4 max-w-lg text-text-muted">
            Sparrow runs on credits, not a subscription. Start with 25 free — enough to find your
            first handful of people and see the messages it writes.
          </p>
        </div>

        <div className="mx-auto mt-10 grid max-w-md gap-3 text-sm sm:max-w-none sm:grid-cols-3">
          {[
            ["1 credit", "per contact discovered"],
            ["2 credits", "per outreach message drafted"],
            ["1 credit", "per MCP tool call that does work"],
          ].map(([amount, label]) => (
            <div
              key={label}
              className="rounded-xl border border-border-subtle bg-surface px-5 py-4 text-center"
            >
              <div className="font-semibold">{amount}</div>
              <div className="mt-1 text-xs text-text-muted">{label}</div>
            </div>
          ))}
        </div>

        <div className="mt-8 grid gap-4 sm:grid-cols-3">
          {(packs ?? []).map((pack, i) => {
            const featured = i === 1;
            return (
              <Card
                key={pack.id}
                className={cn("relative", featured && "border-accent shadow-sm")}
              >
                {featured && (
                  <span className="absolute -top-2.5 left-1/2 -translate-x-1/2 rounded-full bg-accent px-2.5 py-0.5 text-[11px] font-medium text-accent-contrast">
                    Most popular
                  </span>
                )}
                <CardContent className="space-y-4 py-8 text-center">
                  <div className="text-sm font-medium text-text-muted">{pack.name}</div>
                  <div>
                    <span className="text-4xl font-semibold tabular-nums">
                      ${(pack.amount_cents / 100).toFixed(0)}
                    </span>
                  </div>
                  <div className="text-sm text-text-muted">
                    {pack.credits.toLocaleString()} credits
                  </div>
                  <div className="text-xs text-text-subtle">
                    ≈ {Math.floor(pack.credits / 3).toLocaleString()} contacts found and written to
                  </div>
                  <Button
                    className="w-full"
                    variant={featured ? "default" : "outline"}
                    onClick={() => buy(pack.id)}
                  >
                    Buy {pack.name}
                  </Button>
                </CardContent>
              </Card>
            );
          })}
        </div>

        <div className="mx-auto mt-12 max-w-xl">
          <h2 className="text-center text-lg font-semibold">What we commit to</h2>
          <ul className="mt-5 space-y-3">
            {PROMISES.map((promise) => (
              <li key={promise} className="flex items-start gap-3 text-sm">
                <Check className="mt-0.5 h-4 w-4 shrink-0 text-accent" strokeWidth={2.5} />
                <span className="text-text-muted">{promise}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="mt-12 text-center">
          <Button asChild size="lg">
            <Link href="/register">Start with 25 free credits</Link>
          </Button>
        </div>
      </main>

      <MarketingFooter />
    </div>
  );
}
