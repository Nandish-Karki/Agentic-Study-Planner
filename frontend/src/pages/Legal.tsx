import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { GraduationCap } from "lucide-react";

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

// Renders the versioned legal copy served by the backend (/legal/privacy,
// /legal/tos) as plain text. Kept deliberately simple — the authoritative copy
// lives server-side so the consent version recorded at signup matches what's shown.
export default function Legal({ doc, title }: { doc: "privacy" | "tos"; title: string }) {
  const [text, setText] = useState("Loading…");

  useEffect(() => {
    let alive = true;
    fetch(`${BASE}/legal/${doc}`)
      .then((r) => r.text())
      .then((t) => alive && setText(t))
      .catch(() => alive && setText("Could not load this document. Please try again later."));
    return () => {
      alive = false;
    };
  }, [doc]);

  return (
    <div className="min-h-screen bg-ink">
      <header className="border-b border-white/10">
        <div className="max-w-3xl mx-auto px-6 py-5 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2">
            <GraduationCap className="w-6 h-6 text-accent" />
            <span className="font-podium text-xl tracking-wider uppercase">Study Planner</span>
          </Link>
          <Link to="/" className="text-sm text-accent hover:text-indigo-300">
            Back to home
          </Link>
        </div>
      </header>
      <main className="max-w-3xl mx-auto px-6 py-10">
        <h1 className="text-2xl font-bold mb-6">{title}</h1>
        <pre className="whitespace-pre-wrap font-inter text-sm text-slate-300 leading-relaxed">
          {text}
        </pre>
      </main>
    </div>
  );
}
