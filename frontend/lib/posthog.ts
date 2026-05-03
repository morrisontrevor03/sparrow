// eslint-disable-next-line @typescript-eslint/no-explicit-any
let _posthog: any = null;

export function initPostHog() {
  if (typeof window === "undefined") return;
  const key = process.env.NEXT_PUBLIC_POSTHOG_KEY;
  if (!key || _posthog) return;

  import("posthog-js")
    .then(({ default: posthog }) => {
      posthog.init(key, {
        api_host: process.env.NEXT_PUBLIC_POSTHOG_HOST || "https://us.i.posthog.com",
        capture_pageview: true,
        capture_pageleave: true,
        persistence: "localStorage",
      });
      _posthog = posthog;
    })
    .catch(() => {
      // posthog-js not installed — analytics silently disabled
    });
}

export function identifyUser(id: string, email?: string) {
  _posthog?.identify(id, { email });
}

export function track(event: string, props?: Record<string, unknown>) {
  _posthog?.capture(event, props);
}
