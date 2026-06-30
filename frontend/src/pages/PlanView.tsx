import { useEffect, useState, type ReactNode } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, BookOpen, CheckCircle2, AlertTriangle, Download, Printer, GraduationCap, ArrowUpRight } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, type Plan } from "../api/client";
import AppShell from "../components/AppShell";

// Minimal public chrome for the guest demo result (no auth, no account actions).
function GuestShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-ink">
      <header className="border-b border-white/10 print:hidden">
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
      <main className="max-w-6xl mx-auto px-6 py-10">{children}</main>
      <footer className="border-t border-white/10 mt-10 print:hidden">
        <div className="max-w-5xl mx-auto px-6 py-6 flex items-center gap-4 text-xs text-slate-500">
          <Link to="/legal/privacy" className="hover:text-slate-300">Privacy Policy</Link>
          <Link to="/legal/tos" className="hover:text-slate-300">Terms &amp; Conditions</Link>
        </div>
      </footer>
    </div>
  );
}

function unwrapFence(md: string | undefined | null): string {
  const s = (md ?? "").trim();
  if (!s.startsWith("```")) return s;
  const lines = s.split("\n");
  // Scan from the end to find the LAST closing fence — the outer one — so that inner
  // code blocks (which also end with ```) are not mistakenly treated as the close.
  // Content appended after the outer fence (e.g. the budget table) is preserved.
  let closeIdx = -1;
  for (let i = lines.length - 1; i > 0; i--) {
    if (lines[i].trim() === "```") { closeIdx = i; break; }
  }
  if (closeIdx === -1) return s;
  return [...lines.slice(1, closeIdx), ...lines.slice(closeIdx + 1)].join("\n").trim();
}

const mdComponents = {
  table: (props: any) => (
    <div className="overflow-x-auto my-4 rounded-lg border border-white/10">
      <table {...props} />
    </div>
  ),
};

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] px-4 py-3">
      <div className="text-2xl font-semibold text-white">{value}</div>
      <div className="text-[11px] uppercase tracking-wider text-slate-400 mt-0.5">
        {label}
      </div>
    </div>
  );
}

type Tab = "plan" | "profile" | "catalog";

const TAB_LABELS: Record<Tab, string> = {
  plan: "Study Plan",
  profile: "Your Profile",
  catalog: "Module Catalog",
};

export default function PlanView({ guest = false }: { guest?: boolean }) {
  const { id } = useParams<{ id: string }>();
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [plan, setPlan] = useState<Plan | null>(null);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<Tab>("plan");

  useEffect(() => {
    if (!id) return;
    const p = guest ? api.getGuestPlan(id, token) : api.getPlan(id);
    p.then(setPlan).catch((e) => setError(e.message));
  }, [id, guest, token]);

  const Shell = guest ? GuestShell : AppShell;

  const v = plan?.validation;
  const stats = (v?.stats ?? {}) as Record<string, any>;
  const areaCp = (stats.area_cp ?? {}) as Record<string, number>;
  type AreaDetail = { completed: number; planned: number; min: number; max: number; project_cp: number | null };
  const areaDetail = (stats.area_detail ?? {}) as Record<string, AreaDetail>;
  const hasDetail = Object.keys(areaDetail).length > 0;
  const flaggedAreas = new Set(
    (v?.errors ?? [])
      .filter((f) => f.rule.toLowerCase().includes("area"))
      .flatMap((f) => Object.keys(areaCp).filter((a) => f.message.includes(a))),
  );

  function handleDownload() {
    if (!plan) return;
    const date = plan.created_at
      ? new Date(plan.created_at).toLocaleDateString("en-CA")
      : new Date().toLocaleDateString("en-CA");

    const content = [
      `# Your Study Plan — ${date}`,
      "",
      "## Study Plan",
      plan.study_plan_md ?? "",
      "",
      "## Skill Gap Analysis",
      plan.skill_gaps_md ?? "",
      "",
      "## Student Profile",
      plan.profile_md ?? "",
      "",
      "## Module Catalog",
      plan.module_catalog_md ?? "",
    ].join("\n");

    const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "study-plan.md";
    a.click();
    URL.revokeObjectURL(url);
  }

  function handlePrint() {
    window.print();
  }

  const tabs: Tab[] = [
    "plan",
    ...(plan?.profile_md ? (["profile"] as Tab[]) : []),
    ...(!guest && plan?.module_catalog_md ? (["catalog"] as Tab[]) : []),
  ];

  const tabContent: Record<Tab, string> = {
    plan: unwrapFence(plan?.study_plan_md) || "_No plan content._",
    profile: unwrapFence(plan?.profile_md) || "_No profile content._",
    catalog: unwrapFence(plan?.module_catalog_md) || "_No catalog content._",
  };

  return (
    <Shell>
      {guest ? (
        <div className="mb-6 rounded-xl border border-indigo-500/30 bg-indigo-500/10 p-4 flex flex-wrap items-center justify-between gap-3 print:hidden">
          <p className="text-sm text-indigo-100">
            This is a live demo plan generated just now.{" "}
            <span className="font-semibold text-white">Sign up free</span> to build a
            plan from your own transcript and save it.
          </p>
          <Link
            to="/signup"
            className="flex items-center gap-1.5 bg-accent hover:bg-indigo-500 px-4 py-2 rounded-lg text-sm font-semibold transition whitespace-nowrap"
          >
            Sign up to save <ArrowUpRight className="w-4 h-4" />
          </Link>
        </div>
      ) : (
        <Link
          to="/app"
          className="inline-flex items-center gap-1.5 text-slate-400 hover:text-white mb-6 print:hidden"
        >
          <ArrowLeft className="w-4 h-4" /> Back to plans
        </Link>
      )}

      {error && <p className="text-red-400">{error}</p>}
      {!plan && !error && <p className="text-slate-500">Loading…</p>}

      {plan && (
        <div className="space-y-6">
          {/* header */}
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div className="flex items-center gap-3">
              <BookOpen className="w-6 h-6 text-accent shrink-0" />
              <div>
                <h1 className="text-2xl font-semibold leading-tight">Your study plan</h1>
                {plan.created_at && (
                  <p className="text-xs text-slate-500">
                    Generated {new Date(plan.created_at).toLocaleString()}
                  </p>
                )}
              </div>
            </div>
            <div className="flex items-center gap-2 print:hidden">
              <button
                onClick={handleDownload}
                className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-white/10 bg-white/[0.02] text-sm text-slate-300 hover:text-white hover:bg-white/[0.06] transition"
              >
                <Download className="w-4 h-4" />
                Download .md
              </button>
              <button
                onClick={handlePrint}
                className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-white/10 bg-white/[0.02] text-sm text-slate-300 hover:text-white hover:bg-white/[0.06] transition"
              >
                <Printer className="w-4 h-4" />
                Print / PDF
              </button>
            </div>
          </div>

          {/* headline stats */}
          {(stats.semesters != null || stats.planned_modules != null) && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {stats.semesters != null && (
                <Stat label="Semesters" value={stats.semesters} />
              )}
              {stats.planned_modules != null && (
                <Stat label="Planned modules" value={stats.planned_modules} />
              )}
              {stats.completed_modules != null && (
                <Stat label="Already completed" value={stats.completed_modules} />
              )}
              {stats.remaining_coursework_cp != null && (
                <Stat label="Remaining CP" value={stats.remaining_coursework_cp} />
              )}
            </div>
          )}

          {/* validation status — the deterministic trust badge */}
          {v && (
            <div
              className={`rounded-xl border p-4 ${
                v.ok
                  ? "border-emerald-500/30 bg-emerald-500/10"
                  : "border-red-500/30 bg-red-500/10"
              }`}
            >
              <div className="flex items-center gap-2">
                {v.ok ? (
                  <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
                ) : (
                  <AlertTriangle className="w-5 h-5 text-red-400 shrink-0" />
                )}
                <span className="font-semibold">
                  {v.ok
                    ? "Validated — every hard rule checks out"
                    : `${v.errors.length} planning assumption${v.errors.length === 1 ? "" : "s"} that need${v.errors.length === 1 ? "s" : ""} revisiting`}
                </span>
              </div>
              {(v.errors.length > 0 || v.warnings.length > 0) && (
                <ul className="mt-3 space-y-1 text-sm">
                  {v.errors.map((f, i) => (
                    <li key={`e${i}`} className="flex gap-2 text-red-200">
                      <span className="text-red-400">✗</span>
                      <span>{f.message}</span>
                    </li>
                  ))}
                  {v.warnings.map((f, i) => (
                    <li key={`w${i}`} className="flex gap-2 text-amber-200/90">
                      <span className="text-amber-400">!</span>
                      <span>{f.message}</span>
                    </li>
                  ))}
                </ul>
              )}
              <p className="mt-2 text-[11px] text-slate-400">
                Checked in code (not by the AI): credit budgets, prerequisites,
                duplicates, and your remaining-credit total.
              </p>
            </div>
          )}

          {/* tab navigation */}
          {tabs.length > 1 && (
            <div className="flex gap-1 border-b border-white/10 print:hidden">
              {tabs.map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
                    activeTab === tab
                      ? "bg-white/[0.06] text-white border border-b-transparent border-white/10"
                      : "text-slate-400 hover:text-white"
                  }`}
                >
                  {TAB_LABELS[tab]}
                </button>
              ))}
            </div>
          )}

          {/* plan body + sidebar */}
          <div className="grid lg:grid-cols-3 gap-6 items-start">
            <article className="lg:col-span-2 min-w-0 rounded-xl border border-white/10 bg-white/[0.02] p-6 prose-plan">
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
                {tabContent[activeTab]}
              </ReactMarkdown>
            </article>

            <aside className="space-y-6 lg:sticky lg:top-6 print:hidden">
              {hasDetail ? (
                <div className="rounded-xl p-5 border border-white/10 bg-white/[0.02]">
                  <h3 className="text-xs font-semibold uppercase tracking-widest text-slate-400">
                    Credits per area
                  </h3>
                  <p className="text-[11px] text-slate-500 mt-1">
                    completed + planned vs the programme's min–max
                  </p>
                  <ul className="mt-3 space-y-3">
                    {Object.entries(areaDetail).map(([area, d]) => {
                      const total = d.completed + d.planned;
                      const bad = total < d.min || total > d.max;
                      const pct = d.max ? Math.min(100, (total / d.max) * 100) : 0;
                      const minPct = d.max ? Math.min(100, (d.min / d.max) * 100) : 0;
                      return (
                        <li key={area} className="text-sm">
                          <div className="flex justify-between gap-3">
                            <span className={bad ? "text-red-300" : "text-slate-300"}>{area}</span>
                            <span className={`font-semibold whitespace-nowrap ${bad ? "text-red-300" : "text-white"}`}>
                              {total} CP
                            </span>
                          </div>
                          <div className="relative mt-1 h-1.5 rounded bg-white/10">
                            <div
                              className={`absolute inset-y-0 left-0 rounded ${bad ? "bg-red-400/70" : "bg-accent/70"}`}
                              style={{ width: `${pct}%` }}
                            />
                            <div className="absolute inset-y-0 w-px bg-slate-300/60" style={{ left: `${minPct}%` }} />
                          </div>
                          <div className="mt-1 text-[11px] text-slate-500">
                            {d.completed} done + {d.planned} planned · need {d.min}–{d.max}
                            {d.project_cp ? ` · ${d.project_cp} CP project required` : ""}
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ) : (
                Object.keys(areaCp).length > 0 && (
                  <div className="rounded-xl p-5 border border-white/10 bg-white/[0.02]">
                    <h3 className="text-xs font-semibold uppercase tracking-widest text-slate-400">
                      Credits per area
                    </h3>
                    <ul className="mt-3 space-y-2">
                      {Object.entries(areaCp).map(([area, cp]) => {
                        const bad = flaggedAreas.has(area);
                        return (
                          <li key={area} className="flex justify-between gap-3 text-sm">
                            <span className={bad ? "text-red-300" : "text-slate-300"}>{area}</span>
                            <span className={`font-semibold whitespace-nowrap ${bad ? "text-red-300" : "text-white"}`}>
                              {cp} CP
                            </span>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                )
              )}

              {plan.skill_gaps_md && (
                <details
                  className="rounded-xl p-5 border border-white/10 bg-white/[0.02]"
                  open
                >
                  <summary className="text-sm font-semibold cursor-pointer">
                    Skill-gap analysis
                  </summary>
                  <div className="prose-plan mt-3 text-sm">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={mdComponents}
                    >
                      {unwrapFence(plan.skill_gaps_md)}
                    </ReactMarkdown>
                  </div>
                </details>
              )}
            </aside>
          </div>
        </div>
      )}
    </Shell>
  );
}
