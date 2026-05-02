"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { jobs, applications, Job } from "@/lib/api";
import { ExternalLink, X, MapPin, DollarSign, Loader2, Download } from "lucide-react";

function MatchBadge({ score }: { score: number | null }) {
  if (score === null) return null;
  const pct = Math.round(score * 100);
  const color = pct >= 85 ? "text-emerald-400 bg-emerald-400/10" : pct >= 70 ? "text-amber-400 bg-amber-400/10" : "text-zinc-400 bg-white/5";
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${color}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${pct >= 85 ? "bg-emerald-400" : pct >= 70 ? "bg-amber-400" : "bg-zinc-400"}`} />
      {pct}%
    </span>
  );
}

function DraftButton({ job }: { job: Job }) {
  const qc = useQueryClient();

  const slug = job.company.replace(/\s+/g, "_");

  const generateMutation = useMutation({
    mutationFn: () => applications.generate(job.id),
    onSuccess: async (data) => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      try {
        await applications.downloadCoverLetterPdf(data.id, slug);
        await applications.downloadResumePdf(data.id, slug);
      } catch {
        toast.error("Draft created but PDF download failed");
      }
    },
    onError: (err: Error) => toast.error(err.message || "Failed to tailor application"),
  });

  const downloadMutation = useMutation({
    mutationFn: async () => {
      await applications.downloadCoverLetterPdf(job.application_id!, slug);
      await applications.downloadResumePdf(job.application_id!, slug);
    },
    onError: (err: Error) => toast.error(err.message || "Download failed"),
  });

  if (job.application_id) {
    return (
      <button
        onClick={() => downloadMutation.mutate()}
        disabled={downloadMutation.isPending}
        className="inline-flex items-center gap-1.5 text-xs font-medium text-white bg-white/8 hover:bg-white/12 disabled:opacity-60 disabled:cursor-wait rounded-lg px-3 py-1.5 transition-colors"
      >
        {downloadMutation.isPending ? (
          <><Loader2 className="h-3 w-3 animate-spin" /> Downloading…</>
        ) : (
          <><Download className="h-3 w-3" /> Download PDFs</>
        )}
      </button>
    );
  }

  return (
    <button
      onClick={() => generateMutation.mutate()}
      disabled={generateMutation.isPending}
      className="inline-flex items-center gap-1.5 text-xs font-medium text-white bg-white/8 hover:bg-white/12 disabled:opacity-60 disabled:cursor-wait rounded-lg px-3 py-1.5 transition-colors"
    >
      {generateMutation.isPending ? (
        <><Loader2 className="h-3 w-3 animate-spin" /> Tailoring…</>
      ) : "Tailor Application"}
    </button>
  );
}

function JobCard({ job, onDismiss }: { job: Job; onDismiss: (id: string) => void }) {
  return (
    <div className={`rounded-xl border ${job.is_new ? "border-white/12 bg-white/4" : "border-white/6 bg-white/2"} p-5 flex flex-col gap-3 hover:border-white/16 transition-colors`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            {job.is_new && (
              <span className="text-xs font-medium text-blue-400 bg-blue-400/10 px-2 py-0.5 rounded-full">New</span>
            )}
            <MatchBadge score={job.match_score} />
          </div>
          <h3 className="font-medium text-zinc-100 leading-snug">{job.title}</h3>
          <p className="text-sm text-zinc-400 mt-0.5">{job.company}</p>
        </div>
        <button
          onClick={() => onDismiss(job.id)}
          className="shrink-0 text-zinc-600 hover:text-zinc-400 transition-colors"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Meta */}
      <div className="flex flex-wrap items-center gap-3 text-xs text-zinc-500">
        {job.location && (
          <span className="flex items-center gap-1"><MapPin className="h-3 w-3" />{job.location}</span>
        )}
        {(job.salary_min || job.salary_max) && (
          <span className="flex items-center gap-1">
            <DollarSign className="h-3 w-3" />
            {job.salary_min ? `$${(job.salary_min / 1000).toFixed(0)}k` : ""}
            {job.salary_min && job.salary_max ? " – " : ""}
            {job.salary_max ? `$${(job.salary_max / 1000).toFixed(0)}k` : ""}
          </span>
        )}
        {job.employment_type && <span>{job.employment_type.replace("_", " ")}</span>}
      </div>

      {/* Reasoning */}
      {job.match_reasoning && (
        <p className="text-xs text-zinc-400 leading-relaxed line-clamp-2">{job.match_reasoning}</p>
      )}

      <div className="flex items-center gap-2 mt-1">
        <DraftButton job={job} />
        <a
          href={job.url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-200 transition-colors"
        >
          <ExternalLink className="h-3 w-3" /> Original posting
        </a>
      </div>
    </div>
  );
}

export default function JobsPage() {
  const qc = useQueryClient();
  const { data = [], isLoading } = useQuery<Job[]>({
    queryKey: ["jobs"],
    queryFn: () => jobs.list(),
  });

  const dismissMutation = useMutation({
    mutationFn: jobs.dismiss,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
    onError: () => toast.error("Failed to dismiss"),
  });

  if (isLoading) return <div className="animate-pulse text-zinc-500 text-sm">Loading…</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Jobs</h1>
          <p className="text-sm text-zinc-400 mt-1">{data.length} job{data.length !== 1 ? "s" : ""} found</p>
        </div>
      </div>

      {data.length === 0 ? (
        <div className="rounded-xl border border-white/8 bg-white/3 p-12 text-center grid-bg">
          <p className="text-zinc-400 text-sm">No jobs yet. The Job Scout agent runs every 4 hours.</p>
          <p className="text-zinc-500 text-xs mt-2">You can trigger it manually from the Dashboard.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {data.map((job) => (
            <JobCard key={job.id} job={job} onDismiss={(id) => dismissMutation.mutate(id)} />
          ))}
        </div>
      )}
    </div>
  );
}
