"use client";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { Check, Shield } from "lucide-react";
import { LogoMark } from "@/components/brand/Logo";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { connections } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const SCOPE_LABELS: Record<string, string> = {
  "profile:read": "Read your name, headline, and background",
  "campaigns:read": "See your campaigns and their settings",
  "campaigns:run": "Create campaigns and run them — this spends credits",
  "contacts:read": "Read the contacts Sparrow has found for you",
  "contacts:write": "Draft messages and update contacts — this spends credits",
};

function ConsentForm() {
  const params = useSearchParams();
  const { user } = useAuth();
  const [submitting, setSubmitting] = useState(false);

  const clientName = params.get("client_name") || "An MCP client";
  const scopes = (params.get("scope") || "").split(" ").filter(Boolean);

  const decide = async (approved: boolean) => {
    setSubmitting(true);
    try {
      const res = await connections.consent({
        client_id: params.get("client_id") || "",
        redirect_uri: params.get("redirect_uri") || "",
        scope: params.get("scope") || "",
        state: params.get("state") || undefined,
        code_challenge: params.get("code_challenge") || "",
        code_challenge_method: params.get("code_challenge_method") || "S256",
        resource: params.get("resource") || undefined,
        approved,
      });
      window.location.href = res.redirect_url;
    } catch (e) {
      toast.error((e as Error).message);
      setSubmitting(false);
    }
  };

  return (
    <Card>
      <CardContent className="space-y-6 py-8">
        <div className="flex items-center justify-center gap-3">
          <LogoMark className="h-10 w-10" />
          <div className="h-px w-8 bg-border-strong" />
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-surface-sunk">
            <Shield className="h-5 w-5 text-text-muted" />
          </div>
        </div>

        <div className="space-y-1 text-center">
          <h1 className="text-lg font-semibold">
            Connect <span className="text-accent">{clientName}</span> to Sparrow?
          </h1>
          <p className="text-sm text-text-muted">
            Signed in as {user?.email}
          </p>
        </div>

        <div className="space-y-2 rounded-lg border border-border-subtle bg-surface-sunk p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-text-subtle">
            This will let it
          </p>
          {scopes.map((scope) => (
            <div key={scope} className="flex items-start gap-2 text-sm">
              <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent" strokeWidth={2.5} />
              <span>{SCOPE_LABELS[scope] ?? scope}</span>
            </div>
          ))}
        </div>

        <p className="text-center text-xs text-text-subtle">
          You can revoke this any time from Settings → Connections.
        </p>

        <div className="flex gap-3">
          <Button
            variant="outline"
            className="flex-1"
            disabled={submitting}
            onClick={() => decide(false)}
          >
            Cancel
          </Button>
          <Button className="flex-1" disabled={submitting} onClick={() => decide(true)}>
            {submitting ? "Connecting…" : "Allow"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export default function ConsentPage() {
  return (
    <div className="mx-auto max-w-md py-10">
      <Suspense fallback={<Skeleton className="h-96" />}>
        <ConsentForm />
      </Suspense>
    </div>
  );
}
