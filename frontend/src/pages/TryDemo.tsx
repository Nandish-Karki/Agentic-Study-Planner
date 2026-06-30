import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { GraduationCap, Sparkles, ArrowUpRight, AlertTriangle } from "lucide-react";
import { api, ApiError, type Job } from "../api/client";

const ROLES = [
  { id: "data_engineer", label: "Data Engineer",   icon: "⚙️" },
  { id: "ml_engineer",   label: "AI / ML Engineer", icon: "🤖" },
  { id: "data_analyst",  label: "Data Analyst",     icon: "📊" },
] as const;

type PresetRoleId = (typeof ROLES)[number]["id"];

const PHASES = ["Reading the documents", "Planning the semesters", "Validating the plan"];

function phaseIndex(phase: string): number {
  if (phase.startsWith("Validating")) return 2;
  if (phase.startsWith("Planning") || phase.startsWith("Revising")) return 1;
  return 0;
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
        Five agents read a sample student's documents and build the plan — this usually takes 1–2 minutes.
      </p>
    </div>
  );
}

export default function TryDemo() {
  const nav = useNavigate();
  const [preset, setPreset] = useState<PresetRoleId | "other">("data_engineer");
  const [customRole, setCustomRole] = useState("");
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [paused, setPaused] = useState<string | null>(null);

  async function poll(id: string, token: string) {
    for (let i = 0; i < 230; i++) {
      const j = await api.guestPlanStatus(id, token);
      if (j.status === "succeeded")
        return nav(`/try/plan/${id}?token=${encodeURIComponent(token)}`);
      if (j.status === "failed") return void onFailed(j);
      if (j.phase) setPhase(j.phase);
      setStatus(j.phase || `Agents working… (${j.status})`);
      await new Promise((r) => setTimeout(r, 3000));
    }
    setError("This is taking longer than usual — please try again in a minute.");
    setBusy(false);
  }

  function onFailed(j: Job) {
    if (j.failure_reason === "quota_exhausted") {
      setPaused(j.error || "Our free-tier AI quota is used up right now. Please come back later.");
    } else {
      setError(j.error || "The demo run failed. Please try again.");
    }
    setBusy(false);
  }

  function onError(err: unknown) {
    if (err instanceof ApiError && err.status === 429) {
      const q = err.quota;
      setPaused(q?.message || "The demo is busy right now. Please come back later.");
    } else {
      setError(err instanceof ApiError ? err.message : "Could not start the demo.");
    }
    setBusy(false);
  }

  async function run() {
    setError("");
    setPaused(null);
    setBusy(true);
    setStatus("Starting the demo…");
    try {
      const roleValue = preset === "other" ? customRole.trim() || "other" : preset;
      const { job, guest_token } = await api.createGuestDemoPlan(roleValue);
      if (job.status === "succeeded")
        nav(`/try/plan/${job.id}?token=${encodeURIComponent(guest_token)}`);
      else if (job.status === "failed") onFailed(job);
      else poll(job.id, guest_token);
    } catch (err) {
      onError(err);
    }
  }

  return (
    <div className="min-h-screen bg-ink text-white">
      <header className="border-b border-white/10">
        <div className="max-w-5xl mx-auto px-6 py-5 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2">
            <GraduationCap className="w-6 h-6 text-accent" />
            <span className="font-podium text-xl tracking-wider uppercase">Study Planner</span>
          </Link>
          <Link
            to="/signup"
            className="flex items-center gap-1.5 border border-white/30 hover:border-white/60 px-5 py-2 text-xs tracking-widest uppercase hover:bg-white/10 transition"
          >
            Get started <ArrowUpRight className="w-4 h-4" />
          </Link>
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-6 py-16">
        <h1 className="text-3xl font-bold">See the planner in action</h1>
        <p className="mt-3 text-slate-400 leading-relaxed">
          No signup needed. Run a live plan on a sample student — five AI agents read the
          documents, find the skill gaps, and draft a semester-by-semester plan that's then{" "}
          <span className="text-white font-semibold">deterministically checked</span> for
          invented modules, broken prerequisites, and credit-budget violations.
        </p>

        {paused && (
          <div className="mt-6 rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 flex items-start gap-2 text-amber-200 text-sm">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{paused}</span>
          </div>
        )}
        {error && <p className="mt-6 text-red-400">{error}</p>}

        <div className="mt-8">
          <p className="text-sm text-slate-400 mb-3 font-medium">
            What's your target career role?
          </p>
          <div className="flex flex-wrap gap-3 mb-3">
            {ROLES.map((r) => (
              <button
                key={r.id}
                onClick={() => setPreset(r.id)}
                disabled={busy}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg border text-sm font-medium transition disabled:opacity-40 ${
                  preset === r.id
                    ? "border-accent bg-accent/20 text-white"
                    : "border-white/20 bg-white/[0.03] text-slate-300 hover:border-white/40 hover:bg-white/10"
                }`}
              >
                <span>{r.icon}</span>
                {r.label}
              </button>
            ))}
            <button
              onClick={() => setPreset("other")}
              disabled={busy}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg border text-sm font-medium transition disabled:opacity-40 ${
                preset === "other"
                  ? "border-accent bg-accent/20 text-white"
                  : "border-white/20 bg-white/[0.03] text-slate-300 hover:border-white/40 hover:bg-white/10"
              }`}
            >
              <span>✏️</span>
              Other
            </button>
          </div>

          {preset === "other" && (
            <input
              type="text"
              value={customRole}
              onChange={(e) => setCustomRole(e.target.value.slice(0, 60))}
              placeholder="e.g. Backend Engineer, Product Analyst…"
              disabled={busy}
              autoFocus
              className="w-full mb-5 px-4 py-2.5 rounded-lg border border-white/20 bg-white/[0.04] text-white placeholder-slate-500 text-sm focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent disabled:opacity-40"
            />
          )}

          {preset !== "other" && <div className="mb-5" />}

          <button
            onClick={run}
            disabled={busy}
            className="flex items-center gap-2 bg-accent hover:bg-indigo-500 px-6 py-3 rounded-lg font-semibold transition disabled:opacity-50"
          >
            <Sparkles className="w-5 h-5" />
            {busy ? status || "Working…" : "Run the live demo"}
          </button>
          <p className="mt-3 text-xs text-slate-500">
            Want a plan from your own transcript?{" "}
            <Link to="/signup" className="text-accent hover:text-indigo-300">Sign up free</Link>.
          </p>
        </div>

        {busy && (
          <div className="mt-8">
            <ProgressSteps phase={phase} />
          </div>
        )}
      </main>
    </div>
  );
}
