import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, CheckCircle2, AlertTriangle, XCircle } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, type Plan } from "../api/client";
import AppShell from "../components/AppShell";

export default function PlanView() {
  const { id } = useParams<{ id: string }>();
  const [plan, setPlan] = useState<Plan | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!id) return;
    api.getPlan(id).then(setPlan).catch((e) => setError(e.message));
  }, [id]);

  const v = plan?.validation;
  const areaCp = (v?.stats?.area_cp ?? {}) as Record<string, number>;

  return (
    <AppShell>
      <Link to="/app" className="inline-flex items-center gap-1.5 text-slate-400 hover:text-white mb-6">
        <ArrowLeft className="w-4 h-4" /> Back to plans
      </Link>

      {error && <p className="text-red-400">{error}</p>}
      {!plan && !error && <p className="text-slate-500">Loading…</p>}

      {plan && (
        <div className="grid lg:grid-cols-3 gap-8">
          {/* plan body */}
          <article className="lg:col-span-2 prose-plan">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {plan.study_plan_md || "_No plan content._"}
            </ReactMarkdown>
          </article>

          {/* validity sidebar */}
          <aside className="space-y-6">
            {v && (
              <div
                className={`rounded-xl p-5 border ${
                  v.ok
                    ? "border-emerald-500/30 bg-emerald-500/5"
                    : "border-red-500/30 bg-red-500/5"
                }`}
              >
                <div className="flex items-center gap-2">
                  {v.ok ? (
                    <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                  ) : (
                    <XCircle className="w-5 h-5 text-red-400" />
                  )}
                  <span className="font-semibold">
                    {v.ok ? "Validated" : `${v.errors.length} rule issue(s)`}
                  </span>
                </div>
                <p className="text-xs text-slate-400 mt-2">
                  {v.ok
                    ? "Every module is real, nothing is retaken, prerequisites, take-limits, area budgets and credit totals all check out."
                    : "The AI broke a hard rule — caught automatically so you don't follow a broken plan."}
                </p>

                {v.errors.length > 0 && (
                  <ul className="mt-3 space-y-2">
                    {v.errors.map((f, i) => (
                      <li key={i} className="text-xs text-red-300">
                        <span className="font-semibold uppercase">{f.rule}:</span>{" "}
                        {f.message}
                      </li>
                    ))}
                  </ul>
                )}

                {v.warnings.length > 0 && (
                  <details className="mt-3">
                    <summary className="text-xs text-amber-300 cursor-pointer flex items-center gap-1">
                      <AlertTriangle className="w-3.5 h-3.5" />
                      {v.warnings.length} softer warning(s)
                    </summary>
                    <ul className="mt-2 space-y-2">
                      {v.warnings.map((f, i) => (
                        <li key={i} className="text-xs text-amber-200/80">
                          <span className="font-semibold uppercase">{f.rule}:</span>{" "}
                          {f.message}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
              </div>
            )}

            {Object.keys(areaCp).length > 0 && (
              <div className="rounded-xl p-5 border border-white/10 bg-white/[0.02]">
                <h3 className="text-sm font-semibold uppercase tracking-widest text-slate-400">
                  Credits per area
                </h3>
                <ul className="mt-3 space-y-2">
                  {Object.entries(areaCp).map(([area, cp]) => (
                    <li key={area} className="flex justify-between text-sm">
                      <span className="text-slate-300">{area}</span>
                      <span className="text-white font-semibold">{cp} CP</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {plan.skill_gaps_md && (
              <details className="rounded-xl p-5 border border-white/10 bg-white/[0.02]">
                <summary className="text-sm font-semibold cursor-pointer">
                  Skill-gap analysis
                </summary>
                <div className="prose-plan mt-3 text-sm">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {plan.skill_gaps_md}
                  </ReactMarkdown>
                </div>
              </details>
            )}
          </aside>
        </div>
      )}
    </AppShell>
  );
}
