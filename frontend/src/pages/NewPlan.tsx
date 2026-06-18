import { useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { UploadCloud, Sparkles } from "lucide-react";
import { api, ApiError, type Job } from "../api/client";
import AppShell from "../components/AppShell";
import QuotaModal from "../components/QuotaModal";

function FileField({
  label,
  required,
  onChange,
}: {
  label: string;
  required?: boolean;
  onChange: (f: File | null) => void;
}) {
  const [name, setName] = useState("");
  return (
    <label className="block border border-white/10 rounded-lg p-4 bg-white/[0.02] cursor-pointer hover:border-white/25 transition">
      <span className="text-sm text-slate-300">
        {label} {required && <span className="text-accent">*</span>}
      </span>
      <input
        type="file"
        accept="application/pdf"
        required={required}
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0] ?? null;
          setName(f?.name ?? "");
          onChange(f);
        }}
      />
      <div className="mt-1 text-xs text-slate-500 truncate">
        {name || "Choose a PDF…"}
      </div>
    </label>
  );
}

const PHASES = ["Reading your documents", "Planning your semesters", "Validating the plan"];

function phaseIndex(phase: string): number {
  if (phase.startsWith("Validating")) return 2;
  if (phase.startsWith("Planning") || phase.startsWith("Revising")) return 1;
  return 0; // Reading / queued / unknown
}

function ProgressSteps({ phase }: { phase: string }) {
  const active = phaseIndex(phase);
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.02] p-5">
      <ol className="space-y-3">
        {PHASES.map((label, i) => {
          const done = i < active;
          const current = i === active;
          return (
            <li key={label} className="flex items-center gap-3 text-sm">
              <span
                className={`flex h-5 w-5 items-center justify-center rounded-full text-[11px] ${
                  done
                    ? "bg-accent text-white"
                    : current
                      ? "bg-accent/20 text-accent ring-2 ring-accent animate-pulse"
                      : "bg-white/10 text-slate-500"
                }`}
              >
                {done ? "✓" : i + 1}
              </span>
              <span className={current ? "text-white" : done ? "text-slate-400" : "text-slate-500"}>
                {phase && current ? phase : label}
              </span>
            </li>
          );
        })}
      </ol>
      <p className="mt-3 text-xs text-slate-500">
        Five agents read your documents and build the plan — this usually takes 1–2 minutes.
      </p>
    </div>
  );
}

export default function NewPlan() {
  const nav = useNavigate();
  const files = useRef<{
    transcript?: File;
    handbook?: File;
    career?: File;
    cv?: File | null;
  }>({});
  // New first-semester students have no transcript yet — we plan the full degree.
  const [isNew, setIsNew] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [phase, setPhase] = useState("");
  const [error, setError] = useState("");
  // Quota popup: set when our shared free tier (or the user's daily cap) is hit.
  const [quota, setQuota] = useState<{ message?: string; retryAt?: string | null; perUser?: boolean } | null>(null);

  function handleFailedJob(j: Job): boolean {
    // Returns true if it was a quota failure (handled via the modal).
    if (j.failure_reason === "quota_exhausted") {
      setQuota({ retryAt: j.retry_at, perUser: false, message: j.error || undefined });
      setBusy(false);
      return true;
    }
    setError(j.error || "Plan generation failed");
    setBusy(false);
    return false;
  }

  async function poll(id: string) {
    // Poll a little past the backend job_timeout (10 min) so a slow-but-running
    // job is never reported as a frontend timeout while it's still working.
    for (let i = 0; i < 230; i++) {
      const j = await api.planStatus(id);
      if (j.status === "succeeded") return nav(`/app/plan/${id}`);
      if (j.status === "failed") return void handleFailedJob(j);
      if (j.phase) setPhase(j.phase);
      setStatus(j.phase || `Agents working… (${j.status})`);
      await new Promise((r) => setTimeout(r, 3000));
    }
    setError("This is taking longer than usual. Your plan may still finish — check your dashboard in a minute.");
    setBusy(false);
  }

  function proceed(job: Job) {
    if (job.status === "succeeded") nav(`/app/plan/${job.id}`);
    else if (job.status === "failed") handleFailedJob(job);
    else poll(job.id);
  }

  function onError(err: unknown) {
    // Pre-flight 429: our free tier is paused, or the user hit their daily cap.
    if (err instanceof ApiError && err.quota) {
      setQuota({
        message: err.quota.message,
        retryAt: err.quota.retry_at ?? null,
        perUser: err.quota.reason === "daily_user_limit",
      });
    } else {
      setError(err instanceof ApiError ? err.message : "Could not create plan");
    }
    setBusy(false);
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    const { transcript, handbook, career, cv } = files.current;
    if (!handbook || !career) {
      setError("Module handbook and target role are both required.");
      return;
    }
    if (!isNew && !transcript) {
      setError("Transcript is required. If you haven't completed any modules yet, choose “New student”.");
      return;
    }
    setBusy(true);
    setStatus("Uploading and starting the agents…");
    try {
      proceed(
        await api.createPlan(
          { handbook, career, transcript: isNew ? null : transcript, cv },
          { newStudent: isNew },
        ),
      );
    } catch (err) {
      onError(err);
    }
  }

  async function onDemo() {
    setError("");
    setBusy(true);
    setStatus("Starting the demo…");
    try {
      proceed(await api.createDemoPlan());
    } catch (err) {
      onError(err);
    }
  }

  return (
    <AppShell>
      {quota && (
        <QuotaModal
          message={quota.message}
          retryAt={quota.retryAt}
          perUser={quota.perUser}
          onClose={() => setQuota(null)}
        />
      )}
      <h1 className="text-3xl font-bold">New study plan</h1>
      <p className="text-slate-400 mt-1">
        PDFs only. Your documents are processed in memory and deleted after the run.
      </p>
      <p className="mt-2 text-xs text-slate-500">
        Programme:{" "}
        <span className="text-slate-300">Data &amp; Knowledge Engineering (M.Sc.)</span>{" "}
        — Otto-von-Guericke-Universität Magdeburg.{" "}
        <span className="text-slate-600">More programmes coming soon.</span>
      </p>

      <form onSubmit={onSubmit} className="mt-8 space-y-8">
        {/* Continuing vs. new student — a new student has no transcript yet. */}
        <section>
          <h2 className="text-sm font-semibold uppercase tracking-widest text-slate-400 mb-3">
            Where are you in your studies?
          </h2>
          <div className="inline-flex rounded-lg border border-white/10 bg-white/[0.02] p-1">
            <button
              type="button"
              onClick={() => setIsNew(false)}
              className={`px-4 py-2 text-sm rounded-md transition ${
                !isNew ? "bg-accent text-white" : "text-slate-300 hover:text-white"
              }`}
            >
              Continuing student
            </button>
            <button
              type="button"
              onClick={() => setIsNew(true)}
              className={`px-4 py-2 text-sm rounded-md transition ${
                isNew ? "bg-accent text-white" : "text-slate-300 hover:text-white"
              }`}
            >
              New student — 1st semester
            </button>
          </div>
          <p className="mt-2 text-xs text-slate-500">
            {isNew
              ? "No transcript needed — we'll plan the full 90 CP across all thematic areas plus the Master's thesis."
              : "Upload your transcript so we plan only the credits you still need."}
          </p>
        </section>

        <section>
          <h2 className="text-sm font-semibold uppercase tracking-widest text-slate-400 mb-3">
            Documents
          </h2>
          <div className="grid sm:grid-cols-2 gap-4">
            {!isNew && (
              <FileField label="Transcript" required onChange={(f) => (files.current.transcript = f!)} />
            )}
            <FileField label="Module handbook" required onChange={(f) => (files.current.handbook = f!)} />
            <FileField label="Target role / career" required onChange={(f) => (files.current.career = f!)} />
            <FileField label="CV (optional)" onChange={(f) => (files.current.cv = f)} />
          </div>
        </section>

        {error && <p className="text-red-400">{error}</p>}

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={busy}
            className="flex items-center gap-2 bg-accent hover:bg-indigo-500 px-6 py-3 rounded-lg font-semibold transition disabled:opacity-50"
          >
            <UploadCloud className="w-5 h-5" />
            {busy ? status || "Working…" : "Generate my plan"}
          </button>
          <button
            type="button"
            onClick={onDemo}
            disabled={busy}
            className="flex items-center gap-2 px-5 py-3 rounded-lg border border-white/15 text-slate-300 hover:text-white hover:bg-white/[0.06] transition disabled:opacity-50"
          >
            <Sparkles className="w-4 h-4" />
            Try the demo
          </button>
        </div>
        <p className="text-xs text-slate-500 -mt-4">
          No documents handy? "Try the demo" runs a plan on a sample student so you can
          see the result first.
        </p>
        {busy && <ProgressSteps phase={phase} />}
      </form>
    </AppShell>
  );
}
