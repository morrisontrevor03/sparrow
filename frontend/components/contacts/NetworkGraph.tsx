"use client";
import { useMemo, useRef, useState, useCallback, useEffect } from "react";
import { Contact } from "@/lib/api";
import { X } from "lucide-react";

// â”€â”€ Constants â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

const NODE_R = 24;   // person node radius
const HUB_R  = 36;   // company hub radius
const SPOKE_BASE = 80; // minimum spoke length (hub â†’ person)

const STAGE_COLORS: Record<string, string> = {
  discovered:        "var(--text-muted)",
  message_drafted:   "#2563eb",
  sent:              "#7c3aed",
  replied:           "#b45309",
  meeting_scheduled: "#2f8f5b",
};

const STAGE_LABELS: Record<string, string> = {
  discovered:        "Discovered",
  message_drafted:   "Drafted",
  sent:              "Sent",
  replied:           "Replied",
  meeting_scheduled: "Meeting",
};

const STAGE_ORDER = ["discovered", "message_drafted", "sent", "replied", "meeting_scheduled"] as const;

// â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function companyInitials(company: string): string {
  const words = company.trim().split(/\s+/);
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return words.slice(0, 2).map((w) => w[0].toUpperCase()).join("");
}

function personInitials(c: Contact) {
  const parts = [c.first_name, c.last_name].filter(Boolean);
  return parts.length ? parts.map((p) => p![0].toUpperCase()).join("") : "?";
}

function displayName(c: Contact) {
  const name = [c.first_name, c.last_name].filter(Boolean).join(" ") || "Unknown";
  return name.length > 16 ? name.slice(0, 14) + "â€¦" : name;
}

function spokeRadius(memberCount: number): number {
  return Math.max(SPOKE_BASE, 60 + memberCount * 12);
}

// Outer boundary of a cluster: spoke tip + node radius + name label space
function clusterFootprint(memberCount: number): number {
  return spokeRadius(memberCount) + NODE_R + 22;
}

// â”€â”€ Layout types â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

interface HubNode {
  company: string;
  x: number;
  y: number;
  members: Contact[];
}

interface PersonNode {
  contact: Contact;
  x: number;
  y: number;
}

interface SpokeEdge {
  id: string;
  x1: number; y1: number;
  x2: number; y2: number;
}

interface LayoutResult {
  hubs: HubNode[];
  persons: PersonNode[];
  spokes: SpokeEdge[];
}

// â”€â”€ Layout â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function buildLayout(contacts: Contact[]): LayoutResult {
  if (!contacts.length) return { hubs: [], persons: [], spokes: [] };

  const byCompany = new Map<string, Contact[]>();
  for (const c of contacts) {
    const arr = byCompany.get(c.company) ?? [];
    arr.push(c);
    byCompany.set(c.company, arr);
  }

  const companies = Array.from(byCompany.entries()).sort((a, b) => b[1].length - a[1].length);
  const numCompanies = companies.length;

  // Cell size = diameter of the largest cluster + a fixed gap.
  // This guarantees no two adjacent clusters can overlap regardless of member count.
  const maxFootprint = Math.max(...companies.map(([, m]) => clusterFootprint(m.length)));
  const CELL = maxFootprint * 2 + 56;

  const cols    = Math.max(1, Math.ceil(Math.sqrt(numCompanies * 1.3)));
  const numRows = Math.ceil(numCompanies / cols);

  const hubs: HubNode[]     = [];
  const persons: PersonNode[] = [];
  const spokes: SpokeEdge[]  = [];

  companies.forEach(([company, members], i) => {
    const col = i % cols;
    const row = Math.floor(i / cols);
    const cx  = (col - (Math.min(cols, numCompanies) - 1) / 2) * CELL;
    const cy  = (row - (numRows - 1) / 2) * CELL;

    hubs.push({ company, x: cx, y: cy, members });

    const r = spokeRadius(members.length);

    members.forEach((contact, j) => {
      const angle = members.length === 1
        ? -Math.PI / 2
        : (j / members.length) * 2 * Math.PI - Math.PI / 2;

      const px = cx + Math.cos(angle) * r;
      const py = cy + Math.sin(angle) * r;

      persons.push({ contact, x: px, y: py });
      spokes.push({ id: `sp-${company}-${contact.id}`, x1: cx, y1: cy, x2: px, y2: py });
    });
  });

  return { hubs, persons, spokes };
}

// â”€â”€ Company stats panel â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function CompanyPanel({ hub, onClose }: { hub: HubNode; onClose: () => void }) {
  const stageCounts = useMemo(() => {
    const map: Record<string, number> = {};
    for (const c of hub.members) {
      map[c.outreach_status] = (map[c.outreach_status] ?? 0) + 1;
    }
    return map;
  }, [hub.members]);

  const total = hub.members.length;

  // Most advanced stage that has at least one contact
  const dominantStage = [...STAGE_ORDER].reverse().find((s) => (stageCounts[s] ?? 0) > 0) ?? "discovered";
  const dominantColor = STAGE_COLORS[dominantStage];

  const bestScore = Math.max(...hub.members.map((c) => c.relevance_score ?? 0));

  const activeCount = hub.members.filter((c) =>
    c.outreach_status !== "discovered"
  ).length;

  return (
    <div className="absolute top-0 right-0 h-full w-72 bg-surface/95 border-l border-border-subtle flex flex-col shadow-2xl backdrop-blur-sm z-20">
      {/* Header */}
      <div className="flex items-start justify-between gap-3 p-5 border-b border-border-subtle">
        <div className="flex items-center gap-3 min-w-0">
          <div
            className="h-10 w-10 rounded-xl flex items-center justify-center text-sm font-bold shrink-0"
            style={{ background: `${dominantColor}22`, border: `1.5px solid ${dominantColor}55`, color: dominantColor }}
          >
            {companyInitials(hub.company)}
          </div>
          <div className="min-w-0">
            <h3 className="font-semibold text-text text-sm leading-snug truncate">{hub.company}</h3>
            <p className="text-xs text-text-muted mt-0.5">{total} contact{total !== 1 ? "s" : ""}</p>
          </div>
        </div>
        <button onClick={onClose} className="text-text-subtle hover:text-text transition-colors mt-0.5 shrink-0">
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-5 space-y-5">
        {/* Quick stats */}
        <div className="grid grid-cols-2 gap-2.5">
          <div className="rounded-lg bg-surface-sunk border border-border-subtle px-3 py-2.5">
            <p className="text-xs text-text-muted mb-0.5">Active outreach</p>
            <p className="text-lg font-semibold text-text">{activeCount}</p>
          </div>
          <div className="rounded-lg bg-surface-sunk border border-border-subtle px-3 py-2.5">
            <p className="text-xs text-text-muted mb-0.5">Best match</p>
            <p className="text-lg font-semibold" style={{ color: bestScore >= 0.8 ? "#2f8f5b" : bestScore >= 0.6 ? "#b45309" : "var(--text-muted)" }}>
              {Math.round(bestScore * 100)}%
            </p>
          </div>
        </div>

        {/* Stage breakdown */}
        <div className="space-y-2">
          <p className="text-xs font-medium text-text-muted">Pipeline breakdown</p>

          {/* Stacked bar */}
          <div className="flex h-2 rounded-full overflow-hidden gap-px">
            {STAGE_ORDER.map((stage) => {
              const count = stageCounts[stage] ?? 0;
              if (!count) return null;
              return (
                <div
                  key={stage}
                  style={{ flex: count, background: STAGE_COLORS[stage] }}
                />
              );
            })}
          </div>

          {/* Per-stage rows */}
          <div className="space-y-1.5 mt-2">
            {STAGE_ORDER.map((stage) => {
              const count = stageCounts[stage] ?? 0;
              const pct = total ? Math.round((count / total) * 100) : 0;
              return (
                <div key={stage} className="flex items-center gap-2">
                  <div className="h-2 w-2 rounded-full shrink-0" style={{ background: STAGE_COLORS[stage] }} />
                  <span className="text-xs text-text-muted flex-1">{STAGE_LABELS[stage]}</span>
                  <span className="text-xs font-medium text-text">{count}</span>
                  <span className="text-xs text-text-subtle w-8 text-right">{count ? `${pct}%` : "â€”"}</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Contact list preview */}
        <div className="space-y-1.5">
          <p className="text-xs font-medium text-text-muted">Contacts</p>
          {hub.members.map((c) => {
            const name = [c.first_name, c.last_name].filter(Boolean).join(" ") || "Unknown";
            return (
              <div key={c.id} className="flex items-center gap-2.5 py-1.5 border-b border-border-subtle last:border-0">
                <div
                  className="h-6 w-6 rounded-full flex items-center justify-center text-xs font-semibold shrink-0"
                  style={{ background: `${STAGE_COLORS[c.outreach_status]}22`, color: STAGE_COLORS[c.outreach_status] }}
                >
                  {personInitials(c)}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-text truncate">{name}</p>
                  <p className="text-xs text-text-subtle truncate">{c.title || "â€”"}</p>
                </div>
                <div
                  className="h-1.5 w-1.5 rounded-full shrink-0"
                  style={{ background: STAGE_COLORS[c.outreach_status] }}
                  title={STAGE_LABELS[c.outreach_status]}
                />
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// â”€â”€ Graph component â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export function NetworkGraph({
  contacts,
  onSelectContact,
  selectedId,
}: {
  contacts: Contact[];
  onSelectContact: (c: Contact) => void;
  selectedId: string | null;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [pan, setPan]                   = useState({ x: 0, y: 0 });
  const [scale, setScale]               = useState(1);
  const [containerSize, setContainerSize] = useState({ w: 800, h: 600 });
  const [selectedHub, setSelectedHub]   = useState<string | null>(null);
  const isPanning   = useRef(false);
  const lastPointer = useRef({ x: 0, y: 0 });
  const didFit      = useRef(false);

  // Measure container
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      setContainerSize({ w: width, h: height });
    });
    ro.observe(el);
    const { width, height } = el.getBoundingClientRect();
    setContainerSize({ w: width, h: height });
    return () => ro.disconnect();
  }, []);

  const { hubs, persons, spokes } = useMemo(() => buildLayout(contacts), [contacts]);

  // Auto-fit all nodes into view on first load
  useEffect(() => {
    if (didFit.current || !hubs.length || !containerSize.w) return;
    didFit.current = true;

    const pad = 80;
    const xs = hubs.map((h) => h.x);
    const ys = hubs.map((h) => h.y);
    const maxR = Math.max(...hubs.map((h) => spokeRadius(h.members.length)));

    const minX = Math.min(...xs) - maxR - pad;
    const maxX = Math.max(...xs) + maxR + pad;
    const minY = Math.min(...ys) - maxR - pad;
    const maxY = Math.max(...ys) + maxR + pad;

    const contentW = maxX - minX;
    const contentH = maxY - minY;
    const cx = (minX + maxX) / 2;
    const cy = (minY + maxY) / 2;

    const newScale = Math.min(1, containerSize.w / contentW, containerSize.h / contentH);
    // Fit-to-view is the legitimate exception to set-state-in-effect: the scale
    // depends on the measured container, which only exists after layout. The
    // `didFit` guard above makes this run exactly once, so there is no cascade.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setScale(newScale);
    setPan({ x: -cx * newScale, y: -cy * newScale });
  }, [hubs, containerSize]);

  // Zoom toward a point
  const applyZoom = useCallback((factor: number, mouseX: number, mouseY: number) => {
    const halfW = containerSize.w / 2;
    const halfH = containerSize.h / 2;
    setScale((oldScale) => {
      const newScale = Math.min(3, Math.max(0.08, oldScale * factor));
      const ratio    = newScale / oldScale;
      setPan((p) => ({
        x: mouseX - halfW - (mouseX - halfW - p.x) * ratio,
        y: mouseY - halfH - (mouseY - halfH - p.y) * ratio,
      }));
      return newScale;
    });
  }, [containerSize.w, containerSize.h]);

  // Wheel zoom
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const handler = (e: WheelEvent) => {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      applyZoom(e.deltaY > 0 ? 0.88 : 1.14, e.clientX - rect.left, e.clientY - rect.top);
    };
    el.addEventListener("wheel", handler, { passive: false });
    return () => el.removeEventListener("wheel", handler);
  }, [applyZoom]);

  // Pan
  const onPointerDown = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    if ((e.target as Element).closest("[data-node]")) return;
    isPanning.current = true;
    lastPointer.current = { x: e.clientX, y: e.clientY };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  }, []);

  const onPointerMove = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    if (!isPanning.current) return;
    const dx = e.clientX - lastPointer.current.x;
    const dy = e.clientY - lastPointer.current.y;
    setPan((p) => ({ x: p.x + dx, y: p.y + dy }));
    lastPointer.current = { x: e.clientX, y: e.clientY };
  }, []);

  const onPointerUp = useCallback(() => { isPanning.current = false; }, []);

  const halfW     = containerSize.w / 2;
  const halfH     = containerSize.h / 2;
  const transform = `translate(${halfW + pan.x}, ${halfH + pan.y}) scale(${scale})`;

  const activeHub = selectedHub ? hubs.find((h) => h.company === selectedHub) ?? null : null;

  return (
    <div
      ref={containerRef}
      className="relative w-full rounded-xl border border-border-subtle overflow-hidden select-none"
      style={{ height: "calc(100vh - 155px)", minHeight: 400, background: "var(--surface-sunk)" }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerLeave={onPointerUp}
    >
      {/* Dot-grid background */}
      <svg className="absolute inset-0 w-full h-full pointer-events-none" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <pattern
            id="dotgrid"
            width="36"
            height="36"
            patternUnits="userSpaceOnUse"
            patternTransform={`translate(${(halfW + pan.x) % 36}, ${(halfH + pan.y) % 36})`}
          >
            <circle cx="1" cy="1" r="0.9" fill="rgba(255,255,255,0.06)" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#dotgrid)" />
      </svg>

      {/* Main graph */}
      <svg
        width="100%"
        height="100%"
        style={{ display: "block", position: "relative" }}
      >
        <g transform={transform}>
          {/* Spoke edges (hub â†’ person) */}
          {spokes.map((s) => (
            <line
              key={s.id}
              x1={s.x1} y1={s.y1}
              x2={s.x2} y2={s.y2}
              stroke="white"
              strokeOpacity={0.08}
              strokeWidth={1.5}
            />
          ))}

          {/* Person nodes â€” rendered before hubs so hubs sit on top */}
          {persons.map(({ contact, x, y }) => {
            const color      = STAGE_COLORS[contact.outreach_status] ?? "var(--text-muted)";
            const isSelected = selectedId === contact.id;
            return (
              <g
                key={contact.id}
                data-node="true"
                transform={`translate(${x}, ${y})`}
                onClick={() => { onSelectContact(contact); setSelectedHub(null); }}
                style={{ cursor: "pointer" }}
              >
                {isSelected && <circle r={NODE_R + 8} fill="none" stroke="white" strokeWidth={1.5} opacity={0.25} />}
                <circle r={NODE_R + 4} fill="none" stroke={color} strokeWidth={1} opacity={0.2} />
                <circle r={NODE_R} fill="var(--surface)" stroke={color} strokeWidth={2.5} />
                <text
                  textAnchor="middle"
                  dominantBaseline="central"
                  fontSize={10}
                  fontWeight={700}
                  fill="white"
                  style={{ pointerEvents: "none", userSelect: "none" }}
                >
                  {personInitials(contact)}
                </text>
                <text
                  y={NODE_R + 13}
                  textAnchor="middle"
                  fontSize={9.5}
                  fill="var(--text-muted)"
                  style={{ pointerEvents: "none", userSelect: "none" }}
                >
                  {displayName(contact)}
                </text>
              </g>
            );
          })}

          {/* Hub nodes */}
          {hubs.map(({ company, x, y, members }) => {
            const isSelected = selectedHub === company;

            // Dominant stage color for hub accent
            const stageCounts: Record<string, number> = {};
            for (const m of members) stageCounts[m.outreach_status] = (stageCounts[m.outreach_status] ?? 0) + 1;
            const dominant = [...STAGE_ORDER].reverse().find((s) => (stageCounts[s] ?? 0) > 0) ?? "discovered";
            const hubColor = STAGE_COLORS[dominant];

            return (
              <g
                key={`hub-${company}`}
                data-node="true"
                transform={`translate(${x}, ${y})`}
                onClick={() => { setSelectedHub(isSelected ? null : company); }}
                style={{ cursor: "pointer" }}
              >
                {/* Selection ring */}
                {isSelected && (
                  <circle r={HUB_R + 10} fill="none" stroke={hubColor} strokeWidth={1.5} opacity={0.4} />
                )}
                {/* Outer glow */}
                <circle r={HUB_R + 6} fill="none" stroke={hubColor} strokeWidth={1} opacity={0.15} />
                {/* Body â€” square-ish rounded rect feel via larger circle + distinct fill */}
                <circle r={HUB_R} fill="var(--surface)" stroke={hubColor} strokeWidth={2} strokeOpacity={0.6} />
                {/* Company initials */}
                <text
                  textAnchor="middle"
                  dominantBaseline="central"
                  y={-4}
                  fontSize={13}
                  fontWeight={700}
                  fill="white"
                  style={{ pointerEvents: "none", userSelect: "none" }}
                >
                  {companyInitials(company)}
                </text>
                {/* Member count badge */}
                <text
                  textAnchor="middle"
                  dominantBaseline="central"
                  y={10}
                  fontSize={8.5}
                  fill={hubColor}
                  fontWeight={600}
                  style={{ pointerEvents: "none", userSelect: "none" }}
                >
                  {members.length}
                </text>
                {/* Company name label below */}
                <text
                  y={HUB_R + 14}
                  textAnchor="middle"
                  fontSize={10.5}
                  fontWeight={500}
                  fill="var(--text-subtle)"
                  style={{ pointerEvents: "none", userSelect: "none" }}
                >
                  {company.length > 18 ? company.slice(0, 16) + "â€¦" : company}
                </text>
              </g>
            );
          })}
        </g>
      </svg>

      {/* Company stats panel */}
      {activeHub && (
        <CompanyPanel hub={activeHub} onClose={() => setSelectedHub(null)} />
      )}

      {/* Zoom controls */}
      <div
        className="absolute bottom-4 right-4 z-30 flex flex-col gap-1"
        onPointerDown={(e) => e.stopPropagation()}
      >
        <button
          onClick={() => applyZoom(1.25, containerSize.w / 2, containerSize.h / 2)}
          className="h-8 w-8 rounded-lg bg-surface hover:bg-surface-sunk border border-border-subtle text-text flex items-center justify-center text-lg font-light transition-colors"
        >+</button>
        <button
          onClick={() => applyZoom(0.8, containerSize.w / 2, containerSize.h / 2)}
          className="h-8 w-8 rounded-lg bg-surface hover:bg-surface-sunk border border-border-subtle text-text flex items-center justify-center text-lg font-light transition-colors"
        >âˆ’</button>
        <button
          onClick={() => { didFit.current = false; setScale(1); setPan({ x: 0, y: 0 }); }}
          className="h-8 w-8 rounded-lg bg-surface hover:bg-surface-sunk border border-border-subtle text-text-muted flex items-center justify-center text-sm transition-colors"
          title="Fit to view"
        >â†º</button>
      </div>

      {/* Legend */}
      <div
        className="absolute top-3 left-3 z-30 rounded-xl border border-border-subtle bg-surface/95 backdrop-blur-sm p-3 space-y-1.5"
        onPointerDown={(e) => e.stopPropagation()}
      >
        <p className="text-xs font-medium text-text-muted mb-1">Stage</p>
        {STAGE_ORDER.map((key) => (
          <div key={key} className="flex items-center gap-2">
            <div className="h-2 w-2 rounded-full shrink-0" style={{ background: STAGE_COLORS[key] }} />
            <span className="text-xs text-text-muted">{STAGE_LABELS[key]}</span>
          </div>
        ))}
        <div className="border-t border-border-subtle mt-2 pt-2 flex items-center gap-2">
          <div className="h-5 w-5 rounded-full bg-surface border border-border-strong flex items-center justify-center shrink-0">
            <span className="text-white font-bold" style={{ fontSize: 7 }}>AB</span>
          </div>
          <span className="text-xs text-text-muted">Company hub</span>
        </div>
      </div>

      {/* Footer */}
      <div className="absolute bottom-4 left-4 z-30 pointer-events-none">
        <span className="text-xs text-text-subtle">
          {contacts.length} contact{contacts.length !== 1 ? "s" : ""} Â· {hubs.length} compan{hubs.length !== 1 ? "ies" : "y"} Â· click hub for stats
        </span>
      </div>
    </div>
  );
}
