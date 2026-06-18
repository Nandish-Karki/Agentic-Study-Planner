import { Link, useNavigate } from "react-router-dom";
import { GraduationCap, LogOut, AlertTriangle } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { useEffect, useState, type ReactNode } from "react";
import { api, ApiError } from "../api/client";

// Shared chrome for the authenticated dashboard pages.
export default function AppShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const [paused, setPaused] = useState(false);
  // Account deletion (GDPR erasure) — confirm before the irreversible purge.
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");

  async function onDeleteAccount() {
    setDeleting(true);
    setDeleteError("");
    try {
      await api.deleteAccount();
      logout();
      nav("/");
    } catch (err) {
      setDeleteError(err instanceof ApiError ? err.message : "Could not delete your account. Try again.");
      setDeleting(false);
    }
  }

  // Poll the public service status so users see a banner (and know not to bother
  // submitting) when our shared free-tier quota is paused.
  useEffect(() => {
    let alive = true;
    const check = () =>
      api
        .status()
        .then((s) => alive && setPaused(!s.quota_available))
        .catch(() => {});
    check();
    const t = setInterval(check, 60_000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  return (
    <div className="min-h-screen bg-ink">
      {paused && (
        <div className="bg-amber-500/15 border-b border-amber-500/30 text-amber-200 text-sm">
          <div className="max-w-5xl mx-auto px-6 py-2 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            Plan generation is paused — our shared free-tier AI quota is used up for now.
            Please check back later.
          </div>
        </div>
      )}
      <header className="border-b border-white/10">
        <div className="max-w-5xl mx-auto px-6 py-5 flex items-center justify-between">
          <Link to="/app" className="flex items-center gap-2">
            <GraduationCap className="w-6 h-6 text-accent" />
            <span className="font-podium text-xl tracking-wider uppercase">
              Study Planner
            </span>
          </Link>
          <div className="flex items-center gap-4 text-sm">
            <span className="text-slate-400 hidden sm:inline">{user?.email}</span>
            <button
              onClick={() => {
                logout();
                nav("/");
              }}
              className="flex items-center gap-1.5 text-slate-300 hover:text-white transition"
            >
              <LogOut className="w-4 h-4" /> Sign out
            </button>
          </div>
        </div>
      </header>
      <main className="max-w-6xl mx-auto px-6 py-10">{children}</main>

      <footer className="border-t border-white/10 mt-10">
        <div className="max-w-5xl mx-auto px-6 py-6 flex flex-wrap items-center justify-between gap-4 text-xs text-slate-500">
          <div className="flex items-center gap-4">
            <Link to="/legal/privacy" className="hover:text-slate-300">Privacy Policy</Link>
            <Link to="/legal/tos" className="hover:text-slate-300">Terms &amp; Conditions</Link>
          </div>
          <button
            onClick={() => setConfirmDelete(true)}
            className="text-red-400/80 hover:text-red-400 transition"
          >
            Delete my account
          </button>
        </div>
      </footer>

      {confirmDelete && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 px-4">
          <div className="w-full max-w-md rounded-xl border border-white/10 bg-ink p-6">
            <h2 className="text-lg font-semibold text-white">Delete your account?</h2>
            <p className="mt-2 text-sm text-slate-400">
              This permanently erases your account and all your data — every plan, job,
              consent, and audit record. This cannot be undone.
            </p>
            {deleteError && <p className="mt-3 text-sm text-red-400">{deleteError}</p>}
            <div className="mt-6 flex justify-end gap-3">
              <button
                onClick={() => { setConfirmDelete(false); setDeleteError(""); }}
                disabled={deleting}
                className="px-4 py-2 rounded-lg border border-white/15 text-slate-300 hover:text-white hover:bg-white/[0.06] transition disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={onDeleteAccount}
                disabled={deleting}
                className="px-4 py-2 rounded-lg bg-red-600 hover:bg-red-500 text-white font-semibold transition disabled:opacity-50"
              >
                {deleting ? "Deleting…" : "Delete permanently"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
