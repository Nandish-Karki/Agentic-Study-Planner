import { useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { UploadCloud } from "lucide-react";
import { api, ApiError, type Constraints } from "../api/client";
import AppShell from "../components/AppShell";

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

export default function NewPlan() {
  const nav = useNavigate();
  const files = useRef<{ transcript?: File; handbook?: File; career?: File; cv?: File | null }>(
    {},
  );
  const [c, setC] = useState<Constraints & { next_cp: number }>({
    degree_type: "master",
    target_semesters: 3,
    default_cp_per_semester: 30,
    next_cp: 0,
  });
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  async function poll(id: string) {
    for (let i = 0; i < 120; i++) {
      const j = await api.planStatus(id);
      if (j.status === "succeeded") return nav(`/app/plan/${id}`);
      if (j.status === "failed") {
        setError(j.error || "Plan generation failed");
        setBusy(false);
        return;
      }
      setStatus(`Agents working… (${j.status})`);
      await new Promise((r) => setTimeout(r, 3000));
    }
    setError("Timed out waiting for the plan.");
    setBusy(false);
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    const { transcript, handbook, career, cv } = files.current;
    if (!transcript || !handbook || !career) {
      setError("Transcript, handbook, and target role are all required.");
      return;
    }
    setBusy(true);
    setStatus("Uploading and starting the agents…");
    const constraints: Constraints = {
      degree_type: c.degree_type,
      target_semesters: c.target_semesters,
      default_cp_per_semester: c.default_cp_per_semester || null,
      cp_overrides: c.next_cp ? { 1: c.next_cp } : {},
    };
    try {
      const job = await api.createPlan({ transcript, handbook, career, cv }, constraints);
      if (job.status === "succeeded") nav(`/app/plan/${job.id}`);
      else if (job.status === "failed") {
        setError(job.error || "Plan generation failed");
        setBusy(false);
      } else {
        poll(job.id);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create plan");
      setBusy(false);
    }
  }

  const numCls =
    "w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 focus:outline-none focus:ring-2 focus:ring-accent";

  return (
    <AppShell>
      <h1 className="text-3xl font-bold">New study plan</h1>
      <p className="text-slate-400 mt-1">
        PDFs only. Your documents are processed in memory and deleted after the run.
      </p>

      <form onSubmit={onSubmit} className="mt-8 space-y-8">
        <section>
          <h2 className="text-sm font-semibold uppercase tracking-widest text-slate-400 mb-3">
            Documents
          </h2>
          <div className="grid sm:grid-cols-2 gap-4">
            <FileField label="Transcript" required onChange={(f) => (files.current.transcript = f!)} />
            <FileField label="Module handbook" required onChange={(f) => (files.current.handbook = f!)} />
            <FileField label="Target role / career" required onChange={(f) => (files.current.career = f!)} />
            <FileField label="CV (optional)" onChange={(f) => (files.current.cv = f)} />
          </div>
        </section>

        <section>
          <h2 className="text-sm font-semibold uppercase tracking-widest text-slate-400 mb-3">
            Your preferences
          </h2>
          <div className="grid sm:grid-cols-2 gap-4">
            <label className="block">
              <span className="text-sm text-slate-300">Degree</span>
              <select
                value={c.degree_type}
                onChange={(e) => setC({ ...c, degree_type: e.target.value })}
                className={`${numCls} mt-1`}
              >
                <option value="master">Master</option>
                <option value="bachelor">Bachelor</option>
              </select>
            </label>
            <label className="block">
              <span className="text-sm text-slate-300">Finish in (semesters)</span>
              <input
                type="number"
                min={1}
                max={12}
                value={c.target_semesters}
                onChange={(e) => setC({ ...c, target_semesters: +e.target.value })}
                className={`${numCls} mt-1`}
              />
            </label>
            <label className="block">
              <span className="text-sm text-slate-300">Preferred credits / semester</span>
              <input
                type="number"
                min={0}
                max={45}
                value={c.default_cp_per_semester ?? 0}
                onChange={(e) => setC({ ...c, default_cp_per_semester: +e.target.value })}
                className={`${numCls} mt-1`}
              />
            </label>
            <label className="block">
              <span className="text-sm text-slate-300">
                Credits I specifically want next semester (0 = no preference)
              </span>
              <input
                type="number"
                min={0}
                max={45}
                value={c.next_cp}
                onChange={(e) => setC({ ...c, next_cp: +e.target.value })}
                className={`${numCls} mt-1`}
              />
            </label>
          </div>
        </section>

        {error && <p className="text-red-400">{error}</p>}

        <button
          type="submit"
          disabled={busy}
          className="flex items-center gap-2 bg-accent hover:bg-indigo-500 px-6 py-3 rounded-lg font-semibold transition disabled:opacity-50"
        >
          <UploadCloud className="w-5 h-5" />
          {busy ? status || "Working…" : "Generate my plan"}
        </button>
        {busy && (
          <p className="text-sm text-slate-500">
            Five agents are reading your documents — this can take 1–2 minutes.
          </p>
        )}
      </form>
    </AppShell>
  );
}
