"use client";
import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { contacts as contactsApi, agents, settingsApi, Contact, Preferences, AgentRun } from "@/lib/api";
import Link from "next/link";
import { NetworkGraph } from "@/components/networking/NetworkGraph";
import {
  Copy, ExternalLink, Users, Search, X,
  Calendar, Send, MessageSquare, FileEdit, UserPlus, ChevronRight,
  List, Network, Play, Globe, Building2, Trash2,
} from "lucide-react";

// ── Pipeline config ──────────────────────────────────────────────────────

const STAGES = [
  { key: "discovered",        label: "Discovered", shortLabel: "New",     Icon: UserPlus,       color: "text-zinc-300",   bg: "bg-zinc-500/15",   ring: "ring-zinc-500/30" },
  { key: "message_drafted",   label: "Drafted",    shortLabel: "Drafted", Icon: FileEdit,       color: "text-blue-400",   bg: "bg-blue-500/15",   ring: "ring-blue-500/30" },
  { key: "sent",              label: "Sent",       shortLabel: "Sent",    Icon: Send,           color: "text-violet-400", bg: "bg-violet-500/15", ring: "ring-violet-500/30" },
  { key: "replied",           label: "Replied",    shortLabel: "Replied", Icon: MessageSquare,  color: "text-amber-400",  bg: "bg-amber-500/15",  ring: "ring-amber-500/30" },
  { key: "meeting_scheduled", label: "Meeting",    shortLabel: "Meeting", Icon: Calendar,       color: "text-emerald-400",bg: "bg-emerald-500/15",ring: "ring-emerald-500/30" },
] as const;

type StageKey = typeof STAGES[number]["key"];

function stageConfig(key: string) {
  return STAGES.find((s) => s.key === key) ?? STAGES[0];
}

// ── Helpers ──────────────────────────────────────────────────────────────

function initials(c: Contact) {
  const parts = [c.first_name, c.last_name].filter(Boolean);
  return parts.length ? parts.map((p) => p![0].toUpperCase()).join("") : "?";
}

function scoreColor(score: number) {
  if (score >= 0.8) return "text-emerald-400 bg-emerald-400/10";
  if (score >= 0.6) return "text-amber-400 bg-amber-400/10";
  return "text-zinc-400 bg-white/5";
}

// ── Pipeline summary bar ─────────────────────────────────────────────────

function PipelineBar({
  data,
  activeStage,
  onStageClick,
}: {
  data: Contact[];
  activeStage: StageKey | null;
  onStageClick: (key: StageKey | null) => void;
}) {
  const counts = useMemo(() => {
    const map: Record<string, number> = {};
    for (const c of data) map[c.outreach_status] = (map[c.outreach_status] ?? 0) + 1;
    return map;
  }, [data]);

  return (
    <div className="flex gap-2 overflow-x-auto pb-1">
      {STAGES.map(({ key, label, Icon, color, bg, ring }) => {
        const count = counts[key] ?? 0;
        const active = activeStage === key;
        return (
          <button
            key={key}
            onClick={() => onStageClick(active ? null : key)}
            className={`flex items-center gap-2 rounded-xl border px-4 py-2.5 text-sm font-medium transition-all whitespace-nowrap shrink-0
              ${active
                ? `${bg} ring-1 ${ring} border-transparent ${color}`
                : "border-white/8 bg-white/3 text-zinc-400 hover:text-zinc-200 hover:bg-white/6"
              }`}
          >
            <Icon className={`h-3.5 w-3.5 ${active ? color : "text-zinc-500"}`} />
            {label}
            <span className={`text-xs rounded-full px-1.5 py-0.5 font-semibold ${active ? `${bg} ${color}` : "bg-white/8 text-zinc-400"}`}>
              {count}
            </span>
          </button>
        );
      })}
    </div>
  );
}

// ── Contact row ──────────────────────────────────────────────────────────

function ContactRow({
  contact,
  onClick,
}: {
  contact: Contact;
  onClick: () => void;
}) {
  const qc = useQueryClient();
  const update = useMutation({
    mutationFn: (data: Partial<Contact>) => contactsApi.update(contact.id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["contacts"] }),
  });

  const stage = stageConfig(contact.outreach_status);
  const score = contact.relevance_score ?? 0;

  return (
    <div
      className="flex items-center gap-4 px-4 py-3 border-b border-white/5 hover:bg-white/3 cursor-pointer transition-colors group"
      onClick={onClick}
    >
      {/* Avatar */}
      <div className="h-8 w-8 rounded-full bg-white/8 flex items-center justify-center text-xs font-semibold text-zinc-300 shrink-0">
        {initials(contact)}
      </div>

      {/* Name + title */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-zinc-100 truncate">
          {[contact.first_name, contact.last_name].filter(Boolean).join(" ") || "Unknown"}
        </p>
        <p className="text-xs text-zinc-500 truncate">{contact.title || "—"}</p>
      </div>

      {/* Company */}
      <div className="w-36 shrink-0 hidden sm:block">
        <p className="text-xs text-zinc-400 truncate">{contact.company}</p>
      </div>

      {/* Score */}
      <div className="w-16 shrink-0 hidden md:block">
        <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${scoreColor(score)}`}>
          {Math.round(score * 100)}%
        </span>
      </div>

      {/* Status pill */}
      <div className="w-28 shrink-0" onClick={(e) => e.stopPropagation()}>
        <select
          value={contact.outreach_status}
          onChange={(e) => update.mutate({ outreach_status: e.target.value })}
          className={`text-xs rounded-full px-2.5 py-1 border-0 font-medium focus:outline-none focus:ring-1 focus:ring-white/20 cursor-pointer ${stage.bg} ${stage.color}`}
        >
          {STAGES.map((s) => (
            <option key={s.key} value={s.key} className="bg-zinc-900 text-zinc-200">{s.label}</option>
          ))}
        </select>
      </div>

      {/* Quick actions */}
      <div className="flex items-center gap-2 shrink-0" onClick={(e) => e.stopPropagation()}>
        {contact.outreach_message && (
          <button
            onClick={() => {
              navigator.clipboard.writeText(contact.outreach_message!);
              toast.success("Message copied");
            }}
            className="p-1.5 text-zinc-600 hover:text-zinc-300 transition-colors"
            title="Copy outreach message"
          >
            <Copy className="h-3.5 w-3.5" />
          </button>
        )}
        {contact.linkedin_url && (
          <a
            href={contact.linkedin_url}
            target="_blank"
            rel="noopener noreferrer"
            className="p-1.5 text-zinc-600 hover:text-zinc-300 transition-colors"
            title="Open LinkedIn"
          >
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
        )}
        <ChevronRight className="h-3.5 w-3.5 text-zinc-700 group-hover:text-zinc-400 transition-colors" />
      </div>
    </div>
  );
}

// ── Detail drawer ────────────────────────────────────────────────────────

function ContactDrawer({
  contact,
  onClose,
}: {
  contact: Contact;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [notes, setNotes] = useState(contact.notes ?? "");
  const [message, setMessage] = useState(contact.outreach_message ?? "");
  const [notesDirty, setNotesDirty] = useState(false);
  const [messageDirty, setMessageDirty] = useState(false);

  const update = useMutation({
    mutationFn: (data: Partial<Contact>) => contactsApi.update(contact.id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["contacts"] });
      setNotesDirty(false);
      setMessageDirty(false);
      toast.success("Saved");
    },
  });

  const draftMessage = useMutation({
    mutationFn: () => contactsApi.draftMessage(contact.id),
    onSuccess: (updated) => {
      setMessage(updated.outreach_message ?? "");
      setMessageDirty(false);
      qc.invalidateQueries({ queryKey: ["contacts"] });
      toast.success("Message drafted");
    },
    onError: () => toast.error("Failed to draft message"),
  });

  const stage = stageConfig(contact.outreach_status);
  const score = contact.relevance_score ?? 0;
  const fullName = [contact.first_name, contact.last_name].filter(Boolean).join(" ") || "Unknown";

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />

      {/* Panel */}
      <div className="relative w-full max-w-md bg-zinc-950 border-l border-white/8 flex flex-col h-full overflow-y-auto shadow-2xl">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 p-6 border-b border-white/8 sticky top-0 bg-zinc-950 z-10">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-full bg-white/8 flex items-center justify-center text-sm font-semibold text-zinc-200 shrink-0">
              {initials(contact)}
            </div>
            <div>
              <h2 className="font-semibold text-zinc-100">{fullName}</h2>
              <p className="text-sm text-zinc-400">{contact.title || "—"}</p>
            </div>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-200 transition-colors mt-0.5">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 p-6 space-y-6">
          {/* Meta */}
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-lg bg-white/3 border border-white/8 px-3 py-2.5">
              <p className="text-xs text-zinc-500 mb-0.5">Company</p>
              <p className="text-sm text-zinc-200 font-medium">{contact.company}</p>
            </div>
            <div className="rounded-lg bg-white/3 border border-white/8 px-3 py-2.5">
              <p className="text-xs text-zinc-500 mb-0.5">Relevance</p>
              <span className={`text-sm font-semibold ${scoreColor(score).split(" ")[0]}`}>
                {Math.round(score * 100)}%
              </span>
            </div>
            {contact.linkedin_url && (
              <div className="col-span-2 rounded-lg bg-white/3 border border-white/8 px-3 py-2.5 flex items-center justify-between">
                <p className="text-xs text-zinc-500">LinkedIn</p>
                <a
                  href={contact.linkedin_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1.5 text-xs text-zinc-300 hover:text-white transition-colors"
                >
                  View profile <ExternalLink className="h-3 w-3" />
                </a>
              </div>
            )}
            {contact.email && (
              <div className="col-span-2 rounded-lg bg-white/3 border border-white/8 px-3 py-2.5 flex items-center justify-between">
                <p className="text-xs text-zinc-500">Email</p>
                <a
                  href={`mailto:${contact.email}`}
                  className="text-xs text-zinc-300 hover:text-white transition-colors"
                >
                  {contact.email}
                </a>
              </div>
            )}
          </div>

          {/* Status */}
          <div className="space-y-2">
            <label className="text-xs font-medium text-zinc-400">Pipeline stage</label>
            <div className="flex flex-wrap gap-2">
              {STAGES.map(({ key, label, Icon, color, bg, ring }) => {
                const active = contact.outreach_status === key;
                return (
                  <button
                    key={key}
                    onClick={() => update.mutate({ outreach_status: key })}
                    className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-all border
                      ${active
                        ? `${bg} ${color} ring-1 ${ring} border-transparent`
                        : "border-white/8 bg-white/3 text-zinc-500 hover:text-zinc-300"
                      }`}
                  >
                    <Icon className="h-3 w-3" /> {label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Why they were surfaced */}
          {contact.relevance_reasoning && (
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-zinc-400">Why they were surfaced</label>
              <p className="text-xs text-zinc-500 leading-relaxed rounded-lg bg-white/3 border border-white/8 p-3">
                {contact.relevance_reasoning}
              </p>
            </div>
          )}

          {/* Outreach message */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-xs font-medium text-zinc-400">Outreach message</label>
              <div className="flex items-center gap-2">
                {message && (
                  <button
                    onClick={() => { navigator.clipboard.writeText(message); toast.success("Copied"); }}
                    className="flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
                  >
                    <Copy className="h-3 w-3" /> Copy
                  </button>
                )}
                <button
                  onClick={() => draftMessage.mutate()}
                  disabled={draftMessage.isPending}
                  className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 transition-colors disabled:opacity-50"
                >
                  <FileEdit className="h-3 w-3" />
                  {draftMessage.isPending ? "Drafting…" : message ? "Redraft" : "Draft message"}
                </button>
              </div>
            </div>
            <textarea
              value={message}
              onChange={(e) => { setMessage(e.target.value); setMessageDirty(true); }}
              rows={5}
              className="w-full rounded-lg border border-white/8 bg-white/5 px-3 py-2.5 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-white/20 resize-none leading-relaxed"
              placeholder="Click 'Draft message' to generate a personalised outreach…"
            />
            {messageDirty && (
              <button
                onClick={() => update.mutate({ outreach_message: message })}
                disabled={update.isPending}
                className="text-xs text-zinc-300 bg-white/8 hover:bg-white/12 rounded-lg px-3 py-1.5 transition-colors disabled:opacity-50"
              >
                Save message
              </button>
            )}
          </div>

          {/* Notes */}
          <div className="space-y-2">
            <label className="text-xs font-medium text-zinc-400">Notes</label>
            <textarea
              value={notes}
              onChange={(e) => { setNotes(e.target.value); setNotesDirty(true); }}
              rows={4}
              placeholder="Add private notes about this contact…"
              className="w-full rounded-lg border border-white/8 bg-white/5 px-3 py-2.5 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-white/20 resize-none"
            />
            {notesDirty && (
              <button
                onClick={() => update.mutate({ notes })}
                disabled={update.isPending}
                className="text-xs text-zinc-300 bg-white/8 hover:bg-white/12 rounded-lg px-3 py-1.5 transition-colors disabled:opacity-50"
              >
                Save notes
              </button>
            )}
          </div>

          {/* Discovered */}
          {contact.discovered_at && (
            <p className="text-xs text-zinc-600">
              Discovered {new Date(contact.discovered_at).toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" })}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Main page ────────────────────────────────────────────────────────────

type ViewMode = "list" | "graph";

export default function NetworkingPage() {
  const { data = [], isLoading } = useQuery<Contact[]>({
    queryKey: ["contacts"],
    queryFn: () => contactsApi.list(),
  });

  const { data: prefs } = useQuery<Preferences>({
    queryKey: ["settings"],
    queryFn: settingsApi.get,
  });

  const { data: runs } = useQuery<AgentRun[]>({
    queryKey: ["agent-runs"],
    queryFn: () => agents.runs(),
  });

  const hasCompletedNetworkingRun = runs?.some(
    (r) => r.agent_type === "networking" && r.status === "completed"
  );

  const qc = useQueryClient();

  const [view, setView] = useState<ViewMode>("list");
  const [activeStage, setActiveStage] = useState<StageKey | null>(null);
  const [search, setSearch] = useState("");
  const [companyFilter, setCompanyFilter] = useState("");
  const [selected, setSelected] = useState<Contact | null>(null);
  const [runCompany, setRunCompany] = useState("");
  const [running, setRunning] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const deleteAll = useMutation({
    mutationFn: () => contactsApi.deleteAll(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["contacts"] });
      setConfirmDelete(false);
      toast.success("All contacts deleted");
    },
    onError: () => toast.error("Failed to delete contacts"),
  });

  const targetCompanies = useMemo(
    () => prefs?.target_companies ?? [],
    [prefs]
  );

  const handleRunAgent = async () => {
    setRunning(true);
    try {
      if (runCompany) {
        await agents.runNetworkingForCompany(runCompany);
        toast.success(`Networking agent started for ${runCompany}`);
      } else {
        await agents.runNetworking();
        toast.success("Industry-wide networking agent started");
      }
    } catch {
      toast.error("Failed to start agent");
    } finally {
      setRunning(false);
    }
  };

  const companies = useMemo(
    () => Array.from(new Set(data.map((c) => c.company))).sort(),
    [data]
  );

  const filtered = useMemo(() => {
    return data.filter((c) => {
      if (activeStage && c.outreach_status !== activeStage) return false;
      if (companyFilter && c.company !== companyFilter) return false;
      if (search) {
        const q = search.toLowerCase();
        const name = [c.first_name, c.last_name].filter(Boolean).join(" ").toLowerCase();
        if (!name.includes(q) && !c.company.toLowerCase().includes(q) && !(c.title ?? "").toLowerCase().includes(q))
          return false;
      }
      return true;
    });
  }, [data, activeStage, companyFilter, search]);

  // Keep selected contact fresh after mutations
  const selectedFresh = selected ? (data.find((c) => c.id === selected.id) ?? selected) : null;

  if (isLoading) return <div className="animate-pulse text-zinc-500 text-sm">Loading…</div>;

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-xl font-semibold">Networking</h1>
          <p className="text-sm text-zinc-400 mt-1">{data.length} contact{data.length !== 1 ? "s" : ""}</p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {/* Run agent controls */}
          <div className="flex items-center gap-1.5 rounded-xl border border-white/8 bg-white/3 p-1.5">
            <div className="flex items-center gap-1">
              <button
                onClick={() => setRunCompany("")}
                className={`flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                  runCompany === ""
                    ? "bg-white/10 text-white"
                    : "text-zinc-400 hover:text-zinc-200"
                }`}
                title="Run for all target companies"
              >
                <Globe className="h-3 w-3" />
                All
              </button>
              <button
                onClick={() => {
                  if (runCompany === "" && targetCompanies.length > 0) setRunCompany(targetCompanies[0]);
                }}
                className={`flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                  runCompany !== ""
                    ? "bg-white/10 text-white"
                    : "text-zinc-400 hover:text-zinc-200"
                }`}
                title="Run for one company"
              >
                <Building2 className="h-3 w-3" />
                Single
              </button>
            </div>
            {runCompany !== "" && (
              <select
                value={runCompany}
                onChange={(e) => setRunCompany(e.target.value)}
                className="rounded-lg border border-white/8 bg-zinc-900 px-2 py-1 text-xs text-zinc-200 focus:outline-none focus:ring-1 focus:ring-white/20 max-w-36"
              >
                {targetCompanies.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            )}
            <button
              onClick={handleRunAgent}
              disabled={running || (runCompany !== "" && targetCompanies.length === 0)}
              className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium rounded-lg bg-white/8 text-zinc-200 hover:bg-white/15 hover:text-white disabled:opacity-40 transition-colors"
            >
              <Play className="h-3 w-3" />
              {running ? "Starting…" : "Run"}
            </button>
          </div>

          {/* Delete all */}
          {data.length > 0 && (
            confirmDelete ? (
              <div className="flex items-center gap-1.5 rounded-xl border border-red-500/30 bg-red-500/8 px-3 py-1.5">
                <span className="text-xs text-red-300">Delete all {data.length} contacts?</span>
                <button
                  onClick={() => deleteAll.mutate()}
                  disabled={deleteAll.isPending}
                  className="text-xs font-medium text-red-300 hover:text-red-100 transition-colors disabled:opacity-50"
                >
                  {deleteAll.isPending ? "Deleting…" : "Confirm"}
                </button>
                <button
                  onClick={() => setConfirmDelete(false)}
                  className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
                >
                  Cancel
                </button>
              </div>
            ) : (
              <button
                onClick={() => setConfirmDelete(true)}
                className="flex items-center gap-1.5 rounded-xl border border-white/8 bg-white/3 px-3 py-1.5 text-xs font-medium text-zinc-500 hover:text-red-400 hover:border-red-500/30 transition-colors"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Clear all
              </button>
            )
          )}

          {/* View tabs */}
          {data.length > 0 && (
            <div className="flex items-center gap-1 rounded-xl border border-white/8 bg-white/3 p-1">
              <button
                onClick={() => setView("list")}
                className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                  view === "list"
                    ? "bg-white/10 text-white"
                    : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                <List className="h-3.5 w-3.5" />
                List view
              </button>
              <button
                onClick={() => setView("graph")}
                className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                  view === "graph"
                    ? "bg-white/10 text-white"
                    : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                <Network className="h-3.5 w-3.5" />
                Network view
              </button>
            </div>
          )}
        </div>
      </div>

      {data.length === 0 ? (
        <div className="rounded-xl border border-white/8 bg-white/3 p-12 text-center">
          <Users className="h-8 w-8 text-zinc-600 mx-auto mb-3" />
          <p className="text-zinc-400 text-sm">No contacts yet.</p>
          {hasCompletedNetworkingRun ? (
            <p className="text-zinc-500 text-xs mt-1">
              No matches found — try adding more target companies or expanding your role in{" "}
              <Link href="/settings" className="underline underline-offset-2 hover:text-zinc-300">
                Settings
              </Link>.
            </p>
          ) : (
            <p className="text-zinc-500 text-xs mt-1">
              Set target companies in Settings and run the Networking Agent from the dashboard.
            </p>
          )}
        </div>
      ) : view === "list" ? (
        <>
          {/* Pipeline summary */}
          <PipelineBar data={data} activeStage={activeStage} onStageClick={setActiveStage} />

          {/* Filters */}
          <div className="flex gap-2 flex-wrap">
            <div className="relative flex-1 min-w-48">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-zinc-500" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by name, company, or title…"
                className="w-full rounded-lg border border-white/8 bg-white/5 pl-9 pr-3 py-2 text-sm text-white placeholder:text-zinc-500 focus:outline-none focus:ring-1 focus:ring-white/20"
              />
              {search && (
                <button onClick={() => setSearch("")} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300">
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
            <select
              value={companyFilter}
              onChange={(e) => setCompanyFilter(e.target.value)}
              className="rounded-lg border border-white/8 bg-white/5 px-3 py-2 text-sm text-zinc-300 focus:outline-none focus:ring-1 focus:ring-white/20"
            >
              <option value="">All companies</option>
              {companies.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>

          {/* Contact list */}
          <div className="rounded-xl border border-white/8 overflow-hidden">
            <div className="flex items-center gap-4 px-4 py-2 bg-white/3 border-b border-white/8">
              <div className="w-8 shrink-0" />
              <div className="flex-1 text-xs font-medium text-zinc-500">Name</div>
              <div className="w-36 shrink-0 hidden sm:block text-xs font-medium text-zinc-500">Company</div>
              <div className="shrink-0 hidden md:block text-xs font-medium text-zinc-500 w-16">Score</div>
              <div className="shrink-0 text-xs font-medium text-zinc-500 w-28">Stage</div>
              <div className="shrink-0 w-20" />
            </div>

            {filtered.length === 0 ? (
              <div className="py-10 text-center text-sm text-zinc-500">
                No contacts match your filters.
              </div>
            ) : (
              filtered.map((c) => (
                <ContactRow
                  key={c.id}
                  contact={c}
                  onClick={() => setSelected(c)}
                />
              ))
            )}
          </div>

          {filtered.length > 0 && (
            <p className="text-xs text-zinc-600 text-right">
              {filtered.length} of {data.length} contacts
            </p>
          )}
        </>
      ) : (
        /* Network graph view — shows all contacts, click node to open drawer */
        <NetworkGraph
          contacts={data}
          onSelectContact={setSelected}
          selectedId={selected?.id ?? null}
        />
      )}

      {/* Detail drawer — shared between both views */}
      {selectedFresh && (
        <ContactDrawer contact={selectedFresh} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
