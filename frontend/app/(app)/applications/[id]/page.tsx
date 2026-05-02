"use client";
import { use, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { applications, resume as resumeApi } from "@/lib/api";
import { Copy, Download, ExternalLink, ChevronLeft, Loader2 } from "lucide-react";
import Link from "next/link";

// Simple diff highlight: shows which bullets changed vs original
function BulletDiff({
  original,
  tailored,
}: {
  original: string[];
  tailored: string[];
}) {
  const tailoredSet = new Set(tailored);
  const originalSet = new Set(original);

  return (
    <div className="space-y-1.5">
      {tailored.map((bullet, i) => {
        const isNew = !originalSet.has(bullet);
        return (
          <div
            key={i}
            className={`rounded-lg px-3 py-2 text-sm leading-relaxed ${
              isNew
                ? "bg-emerald-400/8 border border-emerald-400/20 text-emerald-100"
                : "bg-white/3 border border-white/6 text-zinc-300"
            }`}
          >
            {isNew && (
              <span className="text-xs font-medium text-emerald-400 mr-2">tailored</span>
            )}
            {bullet}
          </div>
        );
      })}
    </div>
  );
}

export default function ApplicationDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const qc = useQueryClient();
  const [activeTab, setActiveTab] = useState<"resume" | "cover">("resume");
  const [coverLetter, setCoverLetter] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);

  const { data: app, isLoading } = useQuery({
    queryKey: ["application", id],
    queryFn: () => applications.get(id),
    select: (data) => {
      if (coverLetter === null && data.cover_letter) setCoverLetter(data.cover_letter);
      return data;
    },
  });

  const { data: originalResume } = useQuery({
    queryKey: ["resume-active"],
    queryFn: resumeApi.active,
  });

  const saveCoverLetter = useMutation({
    mutationFn: (text: string) => applications.updateCoverLetter(id, text),
    onSuccess: () => { toast.success("Cover letter saved"); setEditing(false); },
    onError: () => toast.error("Failed to save"),
  });

  const slug = app?.job?.company?.replace(/\s+/g, "_") ?? id;

  const downloadCoverLetter = useMutation({
    mutationFn: () => applications.downloadCoverLetterPdf(id, slug),
    onError: () => toast.error("Cover letter download failed"),
  });

  const downloadResume = useMutation({
    mutationFn: () => applications.downloadResumePdf(id, slug),
    onError: () => toast.error("Resume download failed"),
  });

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text).then(() => toast.success(`${label} copied`));
  };

  if (isLoading) return <div className="animate-pulse text-zinc-500 text-sm">Loading…</div>;
  if (!app) return <div className="text-zinc-500 text-sm">Application not found</div>;

  const tailoredExp: Array<{ company: string; role: string; bullets: string[] }> =
    (app.tailored_resume as Record<string, unknown>)?.experience as typeof tailoredExp ?? [];
  const originalExp = originalResume?.structured_data?.experience ?? [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start gap-4">
        <Link href="/applications" className="mt-1 text-zinc-500 hover:text-zinc-300 transition-colors">
          <ChevronLeft className="h-5 w-5" />
        </Link>
        <div className="flex-1">
          <h1 className="text-xl font-semibold">{app.job?.title ?? "Application Draft"}</h1>
          <div className="flex items-center gap-3 mt-1">
            <span className="text-sm text-zinc-400">{app.job?.company}</span>
            {app.job?.location && <span className="text-xs text-zinc-500">{app.job.location}</span>}
            {app.job?.url && (
              <a
                href={app.job.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300"
              >
                <ExternalLink className="h-3 w-3" /> View posting
              </a>
            )}
          </div>
        </div>
        <button
          onClick={() => downloadCoverLetter.mutate()}
          disabled={downloadCoverLetter.isPending}
          className="inline-flex items-center gap-1.5 shrink-0 text-xs font-medium text-zinc-300 bg-white/5 hover:bg-white/10 border border-white/8 disabled:opacity-50 disabled:cursor-wait rounded-lg px-3 py-1.5 transition-colors"
        >
          {downloadCoverLetter.isPending ? (
            <><Loader2 className="h-3.5 w-3.5 animate-spin" /> Downloading…</>
          ) : (
            <><Download className="h-3.5 w-3.5" /> Cover Letter</>
          )}
        </button>
        <button
          onClick={() => downloadResume.mutate()}
          disabled={downloadResume.isPending}
          className="inline-flex items-center gap-1.5 shrink-0 text-xs font-medium text-zinc-300 bg-white/5 hover:bg-white/10 border border-white/8 disabled:opacity-50 disabled:cursor-wait rounded-lg px-3 py-1.5 transition-colors"
        >
          {downloadResume.isPending ? (
            <><Loader2 className="h-3.5 w-3.5 animate-spin" /> Downloading…</>
          ) : (
            <><Download className="h-3.5 w-3.5" /> Resume</>
          )}
        </button>
      </div>

      {/* Tailoring notes */}
      {app.tailoring_notes && (
        <div className="rounded-xl border border-blue-400/15 bg-blue-400/5 p-4">
          <p className="text-xs font-medium text-blue-400 mb-1">What was tailored</p>
          <p className="text-sm text-zinc-300 leading-relaxed">{app.tailoring_notes}</p>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 border-b border-white/8">
        {(["resume", "cover"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab
                ? "border-white text-white"
                : "border-transparent text-zinc-400 hover:text-zinc-200"
            }`}
          >
            {tab === "resume" ? "Tailored Resume" : "Cover Letter"}
          </button>
        ))}
      </div>

      {/* Resume tab */}
      {activeTab === "resume" && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <p className="text-sm text-zinc-400">
              Green bullets were tailored to match the job description.
            </p>
            <div className="flex items-center gap-2">
              <button
                onClick={() => {
                  const text = tailoredExp
                    .map((e) => `${e.role} at ${e.company}\n${e.bullets.map((b) => `• ${b}`).join("\n")}`)
                    .join("\n\n");
                  copyToClipboard(text, "Resume");
                }}
                className="flex items-center gap-1.5 text-xs font-medium text-zinc-300 bg-white/5 hover:bg-white/10 border border-white/8 rounded-lg px-3 py-1.5 transition-colors"
              >
                <Copy className="h-3.5 w-3.5" /> Copy
              </button>
            </div>
          </div>

          {tailoredExp.length > 0 ? (
            <div className="space-y-6">
              {tailoredExp.map((exp, i) => {
                const orig = originalExp.find((e) => e.company === exp.company && e.role === exp.role);
                return (
                  <div key={i}>
                    <div className="mb-2">
                      <h3 className="font-medium text-zinc-100">{exp.role}</h3>
                      <p className="text-sm text-zinc-400">{exp.company}</p>
                    </div>
                    <BulletDiff original={orig?.bullets ?? []} tailored={exp.bullets} />
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-sm text-zinc-500">No experience sections found in the tailored resume.</p>
          )}
        </div>
      )}

      {/* Cover letter tab */}
      {activeTab === "cover" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-zinc-400">Edit if needed, then copy to use in your application.</p>
            <div className="flex items-center gap-2">
              {!editing && (
                <button
                  onClick={() => setEditing(true)}
                  className="text-xs font-medium text-zinc-300 bg-white/5 hover:bg-white/10 border border-white/8 rounded-lg px-3 py-1.5 transition-colors"
                >
                  Edit
                </button>
              )}
              <button
                onClick={() => coverLetter && copyToClipboard(coverLetter, "Cover letter")}
                className="flex items-center gap-1.5 text-xs font-medium text-zinc-300 bg-white/5 hover:bg-white/10 border border-white/8 rounded-lg px-3 py-1.5 transition-colors"
              >
                <Copy className="h-3.5 w-3.5" /> Copy
              </button>
            </div>
          </div>

          {editing ? (
            <div className="space-y-3">
              <textarea
                value={coverLetter ?? ""}
                onChange={(e) => setCoverLetter(e.target.value)}
                rows={16}
                className="w-full rounded-xl border border-white/10 bg-white/4 px-4 py-3 text-sm text-zinc-100 leading-relaxed focus:outline-none focus:ring-1 focus:ring-white/20 resize-none"
              />
              <div className="flex gap-2">
                <button
                  onClick={() => coverLetter && saveCoverLetter.mutate(coverLetter)}
                  disabled={saveCoverLetter.isPending}
                  className="text-sm font-medium bg-white text-zinc-900 hover:bg-zinc-100 rounded-lg px-4 py-2 transition-colors disabled:opacity-50"
                >
                  Save
                </button>
                <button
                  onClick={() => { setCoverLetter(app.cover_letter); setEditing(false); }}
                  className="text-sm text-zinc-400 hover:text-zinc-200 px-4 py-2 transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div className="rounded-xl border border-white/8 bg-white/3 px-5 py-5 text-sm text-zinc-300 leading-[1.8] whitespace-pre-wrap">
              {coverLetter ?? "No cover letter generated yet."}
            </div>
          )}
        </div>
      )}

      {/* Apply CTA */}
      {app.job?.url && (
        <div className="sticky bottom-6 flex justify-end">
          <a
            href={app.job.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 rounded-xl bg-white px-5 py-2.5 text-sm font-semibold text-zinc-900 hover:bg-zinc-100 shadow-lg shadow-black/40 transition-colors"
          >
            Apply now <ExternalLink className="h-4 w-4" />
          </a>
        </div>
      )}
    </div>
  );
}
