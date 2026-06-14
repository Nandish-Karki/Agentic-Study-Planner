import { useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowUpRight,
  GraduationCap,
  ShieldCheck,
  Crown,
  X,
} from "lucide-react";

const NAV = [
  { label: "How it works", href: "#how" },
  { label: "Why trust it", href: "#trust" },
  { label: "Sign in", href: "/login" },
];

export default function Landing() {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div className="min-h-screen bg-ink text-white relative overflow-hidden">
      {/* ambient gradient backdrop (VANGUARD-style dark hero, no agency video) */}
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -top-40 -left-40 w-[40rem] h-[40rem] rounded-full bg-indigo-600/20 blur-3xl" />
        <div className="absolute top-1/3 -right-40 w-[35rem] h-[35rem] rounded-full bg-fuchsia-600/10 blur-3xl" />
      </div>

      {/* Navbar */}
      <nav className="relative z-20 px-6 sm:px-10 lg:px-16 py-5 lg:py-7 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2">
          <GraduationCap className="w-7 h-7 text-accent" />
          <span className="font-podium text-2xl sm:text-3xl font-bold uppercase tracking-wider">
            Study&nbsp;Planner
          </span>
        </Link>
        <div className="hidden md:flex items-center gap-8">
          {NAV.map((n) =>
            n.href.startsWith("#") ? (
              <a
                key={n.label}
                href={n.href}
                className="font-inter text-sm text-white/80 tracking-widest uppercase hover:text-white transition"
              >
                {n.label}
              </a>
            ) : (
              <Link
                key={n.label}
                to={n.href}
                className="font-inter text-sm text-white/80 tracking-widest uppercase hover:text-white transition"
              >
                {n.label}
              </Link>
            ),
          )}
          <Link
            to="/signup"
            className="flex items-center gap-1.5 border border-white/30 hover:border-white/60 px-6 py-3 text-xs tracking-widest uppercase hover:bg-white/10 transition"
          >
            Get started <ArrowUpRight className="w-4 h-4" />
          </Link>
        </div>
        <button
          onClick={() => setMenuOpen(true)}
          className="md:hidden flex flex-col space-y-1.5"
          aria-label="Open menu"
        >
          <span className="w-6 h-0.5 bg-white" />
          <span className="w-6 h-0.5 bg-white" />
          <span className="w-4 h-0.5 bg-white" />
        </button>
      </nav>

      {/* Mobile overlay */}
      <div
        className={`md:hidden fixed inset-0 z-50 bg-black/95 backdrop-blur-sm transition-all duration-500 ${
          menuOpen ? "opacity-100 visible" : "opacity-0 invisible"
        }`}
      >
        <div className="px-6 py-5 flex items-center justify-between">
          <span className="font-podium text-2xl font-bold uppercase tracking-wider">
            Study Planner
          </span>
          <button onClick={() => setMenuOpen(false)} aria-label="Close menu">
            <X className="w-7 h-7" />
          </button>
        </div>
        <div className="h-[80vh] flex flex-col items-center justify-center gap-6">
          {NAV.map((n, i) => (
            <a
              key={n.label}
              href={n.href}
              onClick={() => setMenuOpen(false)}
              className="font-podium text-4xl sm:text-5xl uppercase"
              style={{
                transitionDelay: `${i * 80 + 100}ms`,
                opacity: menuOpen ? 1 : 0,
                transform: menuOpen ? "translateY(0)" : "translateY(20px)",
                transition: "all 0.4s ease-out",
              }}
            >
              {n.label}
            </a>
          ))}
          <Link
            to="/signup"
            onClick={() => setMenuOpen(false)}
            className="border border-white/30 px-8 py-4 text-sm tracking-widest uppercase"
          >
            Get started
          </Link>
        </div>
      </div>

      {/* Hero */}
      <header className="relative z-10 max-w-5xl mx-auto px-6 sm:px-10 lg:px-16 pt-16 lg:pt-24 pb-16">
        <div className="flex items-center gap-2 mb-6 lg:mb-8 animate-fade-up">
          <Crown className="w-4 h-4 text-white/70" />
          <span className="text-white/70 text-xs sm:text-sm font-inter tracking-[0.3em] uppercase">
            For students with electives to choose
          </span>
        </div>

        <h1 className="font-podium uppercase leading-[0.92] tracking-tight animate-fade-up-delay-1">
          <span className="block text-[clamp(2.8rem,8vw,7rem)]">Plan.</span>
          <span className="block text-[clamp(2.8rem,8vw,7rem)]">Validate.</span>
          <span className="block text-[clamp(2.8rem,8vw,7rem)] text-accent">
            Graduate.
          </span>
        </h1>

        <p className="mt-6 lg:mt-8 text-white/70 text-sm sm:text-base font-inter leading-relaxed max-w-xl animate-fade-up-delay-2">
          Upload your transcript and module handbook. Five AI agents read them,
          find the skills your target role needs, and draft a semester-by-semester
          plan to close the gap — <span className="text-white font-semibold">and every plan is automatically checked</span> for invented modules, broken prerequisites, and credit-budget violations.
        </p>

        <div className="mt-8 lg:mt-10 flex flex-wrap items-center gap-4 sm:gap-6 animate-fade-up-delay-3">
          <Link
            to="/signup"
            className="group flex items-center gap-2 bg-accent hover:bg-indigo-500 px-5 sm:px-7 py-3 sm:py-4 text-[11px] sm:text-xs tracking-widest uppercase font-semibold transition"
          >
            Build my plan
            <ArrowUpRight className="w-4 h-4 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition" />
          </Link>
          <div className="hidden sm:flex items-center gap-3">
            <ShieldCheck className="w-8 h-8 text-white/50" />
            <div className="text-white/60 text-xs tracking-wider uppercase leading-tight">
              Every plan
              <br />
              deterministically checked
            </div>
          </div>
        </div>

        <div className="mt-10 sm:mt-14 flex flex-wrap gap-8 sm:gap-12 lg:gap-16 animate-fade-up-delay-4">
          {[
            ["5", "AI agents per plan"],
            ["7", "hard rules enforced"],
            ["0", "invented modules tolerated"],
          ].map(([v, l]) => (
            <div key={l}>
              <div className="font-inter text-2xl sm:text-4xl lg:text-5xl font-bold tracking-tight">
                {v}
              </div>
              <div className="text-white/50 text-[9px] sm:text-xs tracking-widest uppercase mt-1">
                {l}
              </div>
            </div>
          ))}
        </div>
      </header>

      {/* How it works */}
      <section id="how" className="relative z-10 max-w-5xl mx-auto px-6 sm:px-10 lg:px-16 py-16">
        <div className="grid sm:grid-cols-3 gap-6">
          {[
            ["1. Upload", "Your transcript, module handbook, and the role you're aiming for."],
            ["2. Agents analyse", "Five specialists extract your profile, the role's must-haves, the real catalog, and your gaps."],
            ["3. Validated plan", "A semester plan where every module is real, nothing is retaken, and the credits add up — checked automatically."],
          ].map(([t, d]) => (
            <div key={t} className="border border-white/10 rounded-xl p-6 bg-white/[0.02]">
              <h3 className="font-semibold text-white">{t}</h3>
              <p className="mt-2 text-sm text-slate-400 leading-relaxed">{d}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Trust / differentiator */}
      <section id="trust" className="relative z-10 max-w-3xl mx-auto px-6 sm:px-10 lg:px-16 py-12">
        <div className="border border-indigo-500/30 bg-indigo-500/5 rounded-xl p-8">
          <h2 className="text-xl font-bold">Why trust an AI with your degree plan?</h2>
          <p className="mt-3 text-slate-300 leading-relaxed">
            Because we don't trust it blindly either. AI models sometimes invent a
            course or break a rule. So every generated plan runs through a{" "}
            <span className="font-semibold text-white">deterministic checker</span>{" "}
            that confirms each module exists in your handbook, isn't one you've
            passed, respects prerequisites, take-limits, your thematic-area credit
            budgets, your target number of semesters, and that the credits add up.
            If the AI slips, you see exactly where — you never follow a broken plan.
          </p>
          <Link
            to="/signup"
            className="inline-flex items-center gap-2 mt-6 text-accent hover:text-indigo-300 text-sm font-semibold uppercase tracking-widest transition"
          >
            Get started <ArrowUpRight className="w-4 h-4" />
          </Link>
        </div>
      </section>

      <footer className="relative z-10 border-t border-white/10 py-10 text-center text-xs text-slate-500">
        <p>
          Plans are AI-generated guidance, not official academic advice. Your
          documents are processed in memory and never stored.
        </p>
        <p className="mt-2">
          <a href="/legal/privacy" className="hover:text-slate-300">Privacy</a> ·{" "}
          <a href="/legal/tos" className="hover:text-slate-300">Terms</a>
        </p>
      </footer>
    </div>
  );
}
