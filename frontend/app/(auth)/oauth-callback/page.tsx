"use client";
import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

export default function OAuthCallbackPage() {
  const router = useRouter();
  const { login } = useAuth();
  // The token is single-use; a re-run from a changed `login` identity would
  // exchange it twice.
  const handled = useRef(false);

  useEffect(() => {
    if (handled.current) return;
    handled.current = true;

    const params = new URLSearchParams(window.location.search);
    const token = params.get("token");
    const next = params.get("next") ?? "dashboard";

    if (!token) {
      router.replace("/login?error=oauth_failed");
      return;
    }
    login(token).then(() => router.replace(`/${next}`));
  }, [login, router]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface">
      <div className="flex flex-col items-center gap-3">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-border-strong border-t-accent" />
        <p className="text-sm text-text-muted">Signing you in…</p>
      </div>
    </div>
  );
}
