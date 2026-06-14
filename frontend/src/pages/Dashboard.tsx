import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Plus, Trash2, FileText } from "lucide-react";
import { api, type Job } from "../api/client";
import AppShell from "../components/AppShell";

const STATUS_STYLE: Record<string, string> = {
  succeeded: "bg-emerald-500/15 text-emerald-300",
  failed: "bg-red-500/15 text-red-300",
  running: "bg-amber-500/15 text-amber-300",
  queued: "bg-slate-500/15 text-slate-300",
};

export default function Dashboard() {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [error, setError] = useState("");

  async function load() {
    try {
      setJobs(await api.listPlans());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load plans");
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function remove(id: string) {
    if (!confirm("Delete this plan? This cannot be undone.")) return;
    await api.deletePlan(id);
    load();
  }

  return (
    <AppShell>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold">Your plans</h1>
          <p className="text-slate-400 mt-1">
            Each plan is validated against your handbook's real rules.
          </p>
        </div>
        <Link
          to="/app/new"
          className="flex items-center gap-2 bg-accent hover:bg-indigo-500 px-5 py-3 rounded-lg font-semibold transition"
        >
          <Plus className="w-5 h-5" /> New plan
        </Link>
      </div>

      {error && <p className="text-red-400">{error}</p>}

      {jobs === null ? (
        <p className="text-slate-500">Loading…</p>
      ) : jobs.length === 0 ? (
        <div className="border border-dashed border-white/15 rounded-2xl p-16 text-center">
          <FileText className="w-10 h-10 text-slate-600 mx-auto" />
          <p className="mt-4 text-slate-400">No plans yet.</p>
          <Link
            to="/app/new"
            className="inline-block mt-4 text-accent hover:text-indigo-300 font-semibold"
          >
            Create your first plan →
          </Link>
        </div>
      ) : (
        <div className="space-y-3">
          {jobs.map((j) => (
            <div
              key={j.id}
              className="flex items-center justify-between border border-white/10 rounded-xl p-5 bg-white/[0.02] hover:bg-white/[0.04] transition"
            >
              <div>
                <div className="flex items-center gap-3">
                  <span
                    className={`text-xs px-2.5 py-1 rounded-full uppercase tracking-wide ${
                      STATUS_STYLE[j.status] ?? STATUS_STYLE.queued
                    }`}
                  >
                    {j.status}
                  </span>
                  <span className="text-slate-400 text-sm">
                    {new Date(j.created_at).toLocaleString()}
                  </span>
                </div>
                {j.error && <p className="text-xs text-red-400 mt-2">{j.error}</p>}
              </div>
              <div className="flex items-center gap-3">
                {j.status === "succeeded" && (
                  <Link
                    to={`/app/plan/${j.id}`}
                    className="text-accent hover:text-indigo-300 font-semibold text-sm"
                  >
                    View →
                  </Link>
                )}
                <button
                  onClick={() => remove(j.id)}
                  className="text-slate-500 hover:text-red-400 transition"
                  aria-label="Delete"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </AppShell>
  );
}
