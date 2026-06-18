import { Link, useNavigate } from "react-router-dom";
import { GraduationCap, LogOut, AlertTriangle } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { useEffect, useState, type ReactNode } from "react";
import { api } from "../api/client";

// Shared chrome for the authenticated dashboard pages.
export default function AppShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const [paused, setPaused] = useState(false);

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
    </div>
  );
}
