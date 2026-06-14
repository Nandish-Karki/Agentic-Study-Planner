import { Link, useNavigate } from "react-router-dom";
import { GraduationCap, LogOut } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import type { ReactNode } from "react";

// Shared chrome for the authenticated dashboard pages.
export default function AppShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const nav = useNavigate();

  return (
    <div className="min-h-screen bg-ink">
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
      <main className="max-w-5xl mx-auto px-6 py-10">{children}</main>
    </div>
  );
}
