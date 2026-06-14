import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import AuthCard, { btnCls, inputCls } from "../components/AuthCard";

export default function Signup() {
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<{ verifyToken?: string } | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const res = await api.signup(email, password);
      setDone({ verifyToken: res.verify_token });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Signup failed");
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <AuthCard title="Check your email" subtitle={`We sent a verification link to ${email}.`}>
        <p className="text-sm text-slate-400">
          Click the link in that email to verify your account, then sign in.
        </p>
        {done.verifyToken && (
          // Dev convenience: the backend returns the token when DEBUG=1.
          <button
            onClick={() => nav(`/verify?token=${encodeURIComponent(done.verifyToken!)}`)}
            className={`${btnCls} mt-4`}
          >
            Verify now (dev)
          </button>
        )}
        <Link
          to="/login"
          className="block text-center mt-4 text-sm text-accent hover:text-indigo-300"
        >
          Go to sign in
        </Link>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      title="Create your account"
      subtitle="Free — plan your degree around the job you want"
      footer={
        <>
          Already have an account?{" "}
          <Link to="/login" className="text-accent hover:text-indigo-300">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} className="space-y-4">
        <input
          type="email"
          required
          placeholder="you@university.edu"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className={inputCls}
        />
        <input
          type="password"
          required
          minLength={8}
          placeholder="Password (min 8 characters)"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className={inputCls}
        />
        <label className="flex items-start gap-2 text-xs text-slate-400">
          <input
            type="checkbox"
            checked={consent}
            onChange={(e) => setConsent(e.target.checked)}
            className="mt-0.5"
          />
          <span>
            I accept the{" "}
            <a href="/legal/privacy" className="text-accent hover:underline">
              Privacy Policy
            </a>{" "}
            and{" "}
            <a href="/legal/tos" className="text-accent hover:underline">
              Terms
            </a>
            . I understand my documents are sent to a third-party AI provider to
            generate my plan and are not stored.
          </span>
        </label>
        {error && <p className="text-sm text-red-400">{error}</p>}
        <button type="submit" disabled={busy || !consent} className={btnCls}>
          {busy ? "Creating…" : "Create account"}
        </button>
      </form>
    </AuthCard>
  );
}
