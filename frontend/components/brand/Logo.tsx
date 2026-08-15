/**
 * The Sparrow mark — a bird in flight, drawn as two swept wings.
 *
 * Single source of truth: the old app had this SVG inlined in three separate
 * files plus app/icon.svg, so every brand tweak was a four-file change.
 */
export function LogoMark({ className = "h-7 w-7" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" fill="none" className={className} aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="var(--accent)" />
      <path
        d="M7 19.5c3.6.6 6.6-.5 9-3.2 1.6-1.8 2.6-3.9 3-6.3.3 2.7-.2 5.2-1.4 7.4 1.9-.5 3.5-1.6 4.9-3.2-.5 3.4-2.4 5.9-5.6 7.4-3 1.4-6.3 1.3-9.9-.3l.9-1.4Z"
        fill="var(--accent-contrast)"
      />
      <circle cx="20.5" cy="11" r="1.1" fill="var(--accent-contrast)" opacity="0.85" />
    </svg>
  );
}

export function Wordmark({ className = "" }: { className?: string }) {
  return (
    <span className={`flex items-center gap-2 ${className}`}>
      <LogoMark className="h-7 w-7" />
      <span className="text-[15px] font-semibold tracking-tight text-text">Sparrow</span>
    </span>
  );
}
