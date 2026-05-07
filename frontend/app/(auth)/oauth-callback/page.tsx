"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

export default function OAuthCallbackPage() {
  const router = useRouter();
  const { login } = useAuth();

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = params.get("token");
    const next = params.get("next") ?? "dashboard";
    if (!token) {
      router.replace("/login?error=oauth_failed");
      return;
    }
    login(token).then(() => router.replace(`/${next}`));
  }, []);

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="flex flex-col items-center gap-3">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-white/20 border-t-white" />
        <p className="text-sm text-zinc-400">Signing you in…</p>
      </div>
    </div>
  );
}
