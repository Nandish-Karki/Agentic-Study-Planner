import { useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import AuthCard, { btnCls, inputCls } from "../components/AuthCard";

// Two-step reset on one screen: request a token, then set a new password with it.
// Arriving from the email link (/reset?token=…) skips straight to step two.
export default function ResetPassword() {
  const [params] = useSearchParams();
  const [email, setEmail] = useState("");
  const [token, setToken] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [busy, setBusy] = useState(false);
  const [requested, setRequested] = useState(false);

  useEffect(() => {
    const t = params.get("token");
    if (t) {
      setToken(t);
      setRequested(true);
      setInfo("Enter a new password to finish resetting your account.");
    }
  }, [params]);

  async function request(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const res = await api.resetRequest(email);
      setRequested(true);
      setInfo("If that email exists, a reset link has been sent.");
      if (res.reset_token) setToken(res.reset_token); // dev convenience (DEBUG=1)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }

  async function confirm(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await api.resetConfirm(token, newPassword);
      setInfo("Password updated. You can now sign in.");
      setRequested(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Reset failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthCard
      title="Reset password"
      footer={
        <Link to="/login" className="text-accent hover:text-indigo-300">
          Back to sign in
        </Link>
      }
    >
      {!requested ? (
        <form onSubmit={request} className="space-y-4">
          <input
            type="email"
            required
            placeholder="you@university.edu"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={inputCls}
          />
          {error && <p className="text-sm text-red-400">{error}</p>}
          {info && <p className="text-sm text-emerald-400">{info}</p>}
          <button type="submit" disabled={busy} className={btnCls}>
            {busy ? "Sending…" : "Send reset link"}
          </button>
        </form>
      ) : (
        <form onSubmit={confirm} className="space-y-4">
          <p className="text-sm text-slate-400">{info}</p>
          <input
            type="text"
            required
            placeholder="Reset token (from your email)"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            className={inputCls}
          />
          <input
            type="password"
            required
            minLength={8}
            placeholder="New password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            className={inputCls}
          />
          {error && <p className="text-sm text-red-400">{error}</p>}
          <button type="submit" disabled={busy} className={btnCls}>
            {busy ? "Updating…" : "Set new password"}
          </button>
        </form>
      )}
    </AuthCard>
  );
}
