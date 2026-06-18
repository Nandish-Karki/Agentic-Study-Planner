import { useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import AuthCard, { btnCls, inputCls } from "../components/AuthCard";

export default function Verify() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const [state, setState] = useState<"working" | "ok" | "error">("working");
  const [msg, setMsg] = useState("Verifying your email…");

  // Resend flow (shown when arriving without a token, e.g. the link expired).
  const [email, setEmail] = useState("");
  const [info, setInfo] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!token) {
      setState("error");
      setMsg("");
      return;
    }
    api
      .verify(token)
      .then(() => {
        setState("ok");
        setMsg("Your email is verified. You can now sign in and create plans.");
      })
      .catch((err) => {
        setState("error");
        setMsg(err instanceof ApiError ? err.message : "Verification failed.");
      });
  }, [token]);

  async function resend(e: FormEvent) {
    e.preventDefault();
    setInfo("");
    setBusy(true);
    try {
      await api.resendVerification(email);
      setInfo("If that email is registered and unverified, a new link has been sent. Check your inbox.");
    } catch (err) {
      setInfo(err instanceof ApiError ? err.message : "Could not resend. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthCard title={state === "ok" ? "All set" : "Email verification"}>
      {msg && (
        <p className={`text-sm ${state === "error" ? "text-red-400" : "text-slate-300"}`}>
          {msg}
        </p>
      )}
      {state === "ok" && (
        <Link to="/login" className={`${btnCls} mt-6 block text-center`}>
          Sign in
        </Link>
      )}
      {state === "error" && (
        <form onSubmit={resend} className="space-y-3 mt-4">
          <p className="text-sm text-slate-400">
            Need a new verification link? Enter your email and we'll resend it.
          </p>
          <input
            type="email"
            required
            placeholder="you@university.edu"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={inputCls}
          />
          {info && <p className="text-sm text-emerald-400">{info}</p>}
          <button type="submit" disabled={busy} className={btnCls}>
            {busy ? "Sending…" : "Resend verification email"}
          </button>
          <Link
            to="/login"
            className="block text-center text-sm text-accent hover:text-indigo-300"
          >
            Back to sign in
          </Link>
        </form>
      )}
    </AuthCard>
  );
}
