import Link from "next/link";
import { Wordmark } from "@/components/brand/Logo";
import { Button } from "@/components/ui/button";

export function MarketingNav() {
  return (
    <nav className="relative z-10 mx-auto flex max-w-5xl items-center justify-between px-6 py-5">
      <Link href="/">
        <Wordmark />
      </Link>
      <div className="flex items-center gap-1">
        <Button asChild variant="ghost" size="sm">
          <Link href="/pricing">Pricing</Link>
        </Button>
        <Button asChild variant="ghost" size="sm">
          <Link href="/login">Sign in</Link>
        </Button>
        <Button asChild size="sm">
          <Link href="/register">Get started</Link>
        </Button>
      </div>
    </nav>
  );
}

export function MarketingFooter() {
  return (
    <footer className="mx-auto max-w-5xl border-t border-border-subtle px-6 py-8">
      <div className="flex flex-wrap items-center justify-between gap-4 text-xs text-text-subtle">
        <span>© {new Date().getFullYear()} Sparrow</span>
        <div className="flex gap-4">
          <Link href="/pricing" className="hover:text-text">
            Pricing
          </Link>
          <Link href="/login" className="hover:text-text">
            Sign in
          </Link>
        </div>
      </div>
    </footer>
  );
}
