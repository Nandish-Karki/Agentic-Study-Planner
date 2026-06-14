import { Link } from "react-router-dom";
import { GraduationCap } from "lucide-react";
import type { ReactNode } from "react";

export default function AuthCard({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="min-h-screen bg-ink grid place-items-center px-6 py-12">
      <div className="w-full max-w-sm">
        <Link to="/" className="flex items-center justify-center gap-2 mb-8">
          <GraduationCap className="w-7 h-7 text-accent" />
          <span className="font-podium text-2xl uppercase tracking-wider">
            Study Planner
          </span>
        </Link>
        <div className="border border-white/10 rounded-2xl p-8 bg-white/[0.02]">
          <h1 className="text-2xl font-bold">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-slate-400">{subtitle}</p>}
          <div className="mt-6">{children}</div>
        </div>
        {footer && <div className="mt-6 text-center text-sm text-slate-400">{footer}</div>}
      </div>
    </div>
  );
}

export const inputCls =
  "w-full px-4 py-3 rounded-lg bg-white/5 border border-white/10 text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-accent transition";
export const btnCls =
  "w-full py-3 rounded-lg bg-accent hover:bg-indigo-500 font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed";
