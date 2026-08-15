# Sparrow — frontend

Next.js 16 App Router UI for Sparrow, the outreach agent.

## Running locally

```bash
npm install
npm run dev            # http://localhost:3000
```

The backend must be running too — see `../backend`. Point the frontend at it with
`NEXT_PUBLIC_API_URL` in `.env.local` (defaults to `http://localhost:8000`).

## Checks

```bash
npm run lint
npx tsc --noEmit
npm run test:ci
npm run build
```

## Structure

| Path | What lives there |
|---|---|
| `app/(marketing)` | Landing and pricing, public |
| `app/(auth)` | Login, register, onboarding, OAuth callback |
| `app/(app)` | The signed-in app: dashboard, campaigns, contacts, profile, settings |
| `app/(app)/oauth/consent` | The MCP authorization consent screen |
| `components/ui` | shadcn/ui primitives |
| `components/{brand,campaigns,contacts,layout,marketing}` | Feature components |
| `lib/api.ts` | The single typed API client; all backend calls go through it |

## Styling

Tailwind v4, CSS-first — there is no `tailwind.config.ts`. All design tokens are
declared once in `app/globals.css` and exposed to Tailwind through the
`@theme inline` block, so `bg-surface`, `text-text-muted`, `border-border-subtle`
and friends are real utilities.

**Use the tokens, not raw palette colors.** A `bg-white` or `text-zinc-400` that
sneaks in is invisible until the palette changes and then it's a needle in a
haystack — the previous iteration of this app accumulated 717 of them.

The theme is light-only. Adding dark later means adding a `.dark` variable block
in `globals.css`, not touching components.
