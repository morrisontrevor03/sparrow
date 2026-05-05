"use client";
import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { settingsApi, resume as resumeApi, agents } from "@/lib/api";
import {
  Zap, ChevronRight, Check, Upload, FileText,
  Sparkles, Users, Briefcase, Building2,
} from "lucide-react";

import { track } from "@/lib/posthog";

// ── Types ──────────────────────────────────────────────────────────────────

interface OnboardingState {
  resume_uploaded: boolean;
  resume_filename: string | null;
  target_roles: string[];
  experience_level: string;
  target_locations: string[];
  location_flexible: boolean;
  target_companies: string[];
}

const INITIAL: OnboardingState = {
  resume_uploaded: false,
  resume_filename: null,
  target_roles: [],
  experience_level: "",
  target_locations: [],
  location_flexible: true,
  target_companies: [],
};

const STEPS = ["Resume", "Targets", "Companies", "Launch"] as const;

// ── Shared ─────────────────────────────────────────────────────────────────

function TagInput({
  items,
  onChange,
  placeholder,
}: {
  items: string[];
  onChange: (items: string[]) => void;
  placeholder: string;
}) {
  const [input, setInput] = useState("");
  const add = () => {
    const t = input.trim();
    if (t && !items.includes(t)) onChange([...items, t]);
    setInput("");
  };
  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), add())}
          placeholder={placeholder}
          className="flex-1 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder:text-zinc-500 focus:outline-none focus:ring-1 focus:ring-white/20"
        />
        <button
          type="button"
          onClick={add}
          className="rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-sm text-zinc-300 hover:bg-white/10 transition-colors"
        >
          Add
        </button>
      </div>
      {items.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {items.map((item) => (
            <span
              key={item}
              className="flex items-center gap-1.5 rounded-full border border-white/10 bg-white/8 px-3 py-1 text-xs text-zinc-200"
            >
              {item}
              <button
                type="button"
                onClick={() => onChange(items.filter((i) => i !== item))}
                className="text-zinc-500 hover:text-zinc-300 leading-none"
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Step 0: Resume ─────────────────────────────────────────────────────────

function StepResume({
  state,
  update,
}: {
  state: OnboardingState;
  update: (patch: Partial<OnboardingState>) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  const handleFile = async (file: File) => {
    setUploading(true);
    try {
      const result = await resumeApi.upload(file);
      update({ resume_uploaded: true, resume_filename: result.filename ?? file.name });
      track("resume_uploaded");
      toast.success("Resume parsed successfully");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-semibold">Upload your resume</h2>
        <p className="mt-1 text-sm text-zinc-400">
          Claude parses it once and tailors it for every job you apply to.
        </p>
      </div>

      {state.resume_uploaded ? (
        <div className="flex items-center gap-3 rounded-xl border border-emerald-500/20 bg-emerald-500/8 p-4">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-emerald-500/15">
            <Check className="h-4 w-4 text-emerald-400" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-emerald-300">{state.resume_filename}</p>
            <p className="text-xs text-emerald-400/70 mt-0.5">Parsed and ready</p>
          </div>
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            className="text-xs text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            Replace
          </button>
          <input
            ref={inputRef}
            type="file"
            accept=".pdf,.docx,.doc"
            className="hidden"
            onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
          />
        </div>
      ) : (
        <div
          onClick={() => !uploading && inputRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            const file = e.dataTransfer.files[0];
            if (file) handleFile(file);
          }}
          className={`cursor-pointer rounded-xl border-2 border-dashed p-10 text-center transition-colors ${
            dragOver ? "border-white/30 bg-white/5" : "border-white/10 hover:border-white/20 hover:bg-white/3"
          }`}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".pdf,.docx,.doc"
            className="hidden"
            onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
          />
          {uploading ? (
            <div className="flex flex-col items-center gap-3">
              <div className="h-5 w-5 animate-spin rounded-full border-2 border-white/20 border-t-white" />
              <p className="text-sm text-zinc-400">Parsing with AI…</p>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl border border-white/10 bg-white/5">
                <Upload className="h-5 w-5 text-zinc-400" />
              </div>
              <div>
                <p className="text-sm font-medium text-zinc-200">Drop your resume here</p>
                <p className="text-xs text-zinc-500 mt-1">PDF or DOCX · Max 10 MB</p>
              </div>
            </div>
          )}
        </div>
      )}

      <p className="text-xs text-zinc-600">Required to continue — used to tailor applications to each job.</p>
    </div>
  );
}

// ── Step 1: Targets ────────────────────────────────────────────────────────

function StepTargets({
  state,
  update,
}: {
  state: OnboardingState;
  update: (patch: Partial<OnboardingState>) => void;
}) {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold">What are you targeting?</h2>
        <p className="mt-1 text-sm text-zinc-400">
          Your agents scan for these roles and locations every few hours.
        </p>
      </div>

      <div className="space-y-2">
        <label className="text-xs font-medium text-zinc-400">Job titles <span className="text-red-400">*</span></label>
        <TagInput
          items={state.target_roles}
          onChange={(v) => update({ target_roles: v })}
          placeholder="e.g. Software Engineer, Product Manager"
        />
      </div>

      <div className="space-y-2">
        <label className="text-xs font-medium text-zinc-400">Experience level</label>
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-7">
          {["new_grad", "entry", "junior", "mid", "senior", "staff", "lead"].map((lvl) => (
            <button
              key={lvl}
              type="button"
              onClick={() => update({ experience_level: state.experience_level === lvl ? "" : lvl })}
              className={`rounded-lg border py-2 text-xs font-medium transition-all ${
                state.experience_level === lvl
                  ? "border-white/40 bg-white/10 text-white"
                  : "border-white/8 bg-white/3 text-zinc-400 hover:border-white/20 hover:text-zinc-200"
              }`}
            >
              {lvl === "new_grad" ? "New Grad" : lvl.charAt(0).toUpperCase() + lvl.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-2">
        <label className="text-xs font-medium text-zinc-400">Locations <span className="text-red-400">*</span></label>
        <TagInput
          items={state.target_locations}
          onChange={(v) => update({ target_locations: v })}
          placeholder="e.g. New York, Remote, Austin TX"
        />
        <div className="flex gap-2 pt-1">
          {[
            { value: false, label: "Firm", desc: "Only these locations" },
            { value: true, label: "Flexible", desc: "Also show nearby / remote" },
          ].map(({ value, label, desc }) => (
            <button
              key={label}
              type="button"
              onClick={() => update({ location_flexible: value })}
              className={`flex-1 rounded-xl border p-3 text-left transition-all ${
                state.location_flexible === value
                  ? "border-white/40 bg-white/10"
                  : "border-white/8 bg-white/3 hover:border-white/20"
              }`}
            >
              <p className="text-xs font-medium text-zinc-100">{label}</p>
              <p className="mt-0.5 text-[11px] text-zinc-500">{desc}</p>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Step 2: Companies ──────────────────────────────────────────────────────

function StepCompanies({
  state,
  update,
}: {
  state: OnboardingState;
  update: (patch: Partial<OnboardingState>) => void;
}) {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold">Which companies interest you?</h2>
        <p className="mt-1 text-sm text-zinc-400">
          Aim for 5–10 for best networking results.
        </p>
      </div>

      <TagInput
        items={state.target_companies}
        onChange={(v) => update({ target_companies: v })}
        placeholder="e.g. Stripe, Figma, Airbnb"
      />
      {state.target_companies.length > 0 && state.target_companies.length < 5 && (
        <p className="text-[11px] text-zinc-500">Add {5 - state.target_companies.length} more for best networking results</p>
      )}
    </div>
  );
}

// ── Step 3: Launch ─────────────────────────────────────────────────────────

function StepLaunch({
  state,
  onLaunch,
  launching,
}: {
  state: OnboardingState;
  onLaunch: () => void;
  launching: boolean;
}) {
  const companyDesc = state.target_companies.length > 0
    ? state.target_companies.slice(0, 3).join(", ") + (state.target_companies.length > 3 ? ` +${state.target_companies.length - 3}` : "")
    : "None specified — agents will cast wide";

  const summaryItems = [
    {
      icon: FileText,
      label: "Resume",
      value: state.resume_filename ?? "Uploaded",
    },
    {
      icon: Briefcase,
      label: "Roles",
      value: state.target_roles.length > 0
        ? state.target_roles.slice(0, 3).join(", ") + (state.target_roles.length > 3 ? ` +${state.target_roles.length - 3}` : "")
        : "—",
    },
    {
      icon: Building2,
      label: "Companies",
      value: companyDesc,
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold">You&apos;re set. Let&apos;s find your leads.</h2>
        <p className="mt-1 text-sm text-zinc-400">
          Your agents are ready. Click below to generate your first results.
        </p>
      </div>

      <div className="rounded-xl border border-white/8 bg-white/3 divide-y divide-white/5">
        {summaryItems.map(({ icon: Icon, label, value }) => (
          <div key={label} className="flex items-start gap-3 px-4 py-3">
            <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-white/8 mt-0.5">
              <Icon className="h-3 w-3 text-zinc-400" />
            </div>
            <div className="min-w-0">
              <p className="text-[11px] font-medium text-zinc-500">{label}</p>
              <p className="text-sm text-zinc-200 truncate">{value}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="rounded-xl border border-white/8 bg-white/3 p-4 space-y-2.5">
        <p className="text-xs font-medium text-zinc-400">What happens next</p>
        {[
          { icon: Briefcase, text: "Job Scout finds your top 10 matches from thousands of live postings" },
          { icon: Users, text: "Networking Agent finds warm contacts at your target companies" },
          { icon: Sparkles, text: "You review everything. No auto-applying — ever." },
        ].map(({ icon: Icon, text }) => (
          <div key={text} className="flex items-start gap-2.5">
            <Icon className="h-3.5 w-3.5 text-zinc-500 shrink-0 mt-0.5" />
            <p className="text-xs text-zinc-400">{text}</p>
          </div>
        ))}
      </div>

      <button
        type="button"
        onClick={onLaunch}
        disabled={launching}
        className="w-full flex items-center justify-center gap-2 rounded-xl bg-white px-5 py-3 text-sm font-semibold text-zinc-900 hover:bg-zinc-100 disabled:opacity-50 transition-colors"
      >
        {launching ? (
          <>
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-400 border-t-zinc-900" />
            Launching agents…
          </>
        ) : (
          <>
            <Zap className="h-4 w-4" />
            Generate my first leads
          </>
        )}
      </button>
    </div>
  );
}

// ── Main ───────────────────────────────────────────────────────────────────

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [state, setState] = useState<OnboardingState>(INITIAL);
  const [launching, setLaunching] = useState(false);

  const update = (patch: Partial<OnboardingState>) =>
    setState((s) => ({ ...s, ...patch }));

  const canAdvance = () => {
    if (step === 0) return state.resume_uploaded;
    if (step === 1) return state.target_roles.length > 0 && state.target_locations.length > 0;
    return true;
  };

  const launch = async () => {
    setLaunching(true);
    try {
      await settingsApi.update({
        target_roles: state.target_roles,
        experience_level: state.experience_level || null,
        target_locations: state.target_locations,
        location_flexible: state.location_flexible,
        target_companies: state.target_companies,
      });
      track("first_run_triggered", { roles: state.target_roles.length, companies: state.target_companies.length });
      await Promise.allSettled([agents.runJobScout(), agents.runNetworking()]);
      router.replace("/dashboard?first_run=true");
    } catch {
      toast.error("Something went wrong. Please try again.");
      setLaunching(false);
    }
  };

  const isLast = step === STEPS.length - 1;

  return (
    <div className="flex min-h-screen items-center justify-center bg-zinc-950 grid-bg px-4 py-12">
      <div className="w-full max-w-lg">
        {/* Header */}
        <div className="mb-8 flex flex-col items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 bg-white/5">
            <Zap className="h-5 w-5 text-white" />
          </div>
          <h1 className="text-xl font-semibold">Set up ApplyNow</h1>
          <p className="text-sm text-zinc-400">Takes about 2 minutes.</p>
        </div>

        {/* Step indicators */}
        <div className="mb-6 flex items-center gap-2">
          {STEPS.map((label, i) => (
            <div key={label} className="flex flex-1 flex-col items-center gap-1">
              <div
                className={`h-1 w-full rounded-full transition-all ${
                  i <= step ? "bg-white" : "bg-white/15"
                }`}
              />
              <span
                className={`text-[10px] font-medium ${
                  i === step ? "text-zinc-200" : "text-zinc-600"
                }`}
              >
                {label}
              </span>
            </div>
          ))}
        </div>

        {/* Step content */}
        <div className="rounded-xl border border-white/8 bg-white/3 p-6">
          {step === 0 && <StepResume state={state} update={update} />}
          {step === 1 && <StepTargets state={state} update={update} />}
          {step === 2 && <StepCompanies state={state} update={update} />}
          {step === 3 && <StepLaunch state={state} onLaunch={launch} launching={launching} />}
        </div>

        {/* Navigation */}
        {!isLast && (
          <div className="mt-4 flex items-center justify-between">
            <button
              type="button"
              onClick={step === 0 ? () => router.replace("/dashboard") : () => setStep((s) => s - 1)}
              className="text-sm text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              {step === 0 ? "Skip for now" : "Back"}
            </button>

            <button
              type="button"
              onClick={() => setStep((s) => s + 1)}
              disabled={!canAdvance()}
              className="flex items-center gap-2 rounded-lg bg-white px-5 py-2.5 text-sm font-semibold text-zinc-900 hover:bg-zinc-100 disabled:opacity-40 transition-colors"
            >
              Continue <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        )}
        {isLast && (
          <div className="mt-4 flex justify-start">
            <button
              type="button"
              onClick={() => setStep((s) => s - 1)}
              className="text-sm text-zinc-500 hover:text-zinc-300 transition-colors"
            >
              Back
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
