import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import AuthCard, { btnCls } from "../components/AuthCard";

export default function Verify() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const [state, setState] = useState<"working" | "ok" | "error">("working");
  const [msg, setMsg] = useState("Verifying your email…");

  useEffect(() => {
    if (!token) {
      setState("error");
      setMsg("Missing verification token.");
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

  return (
    <AuthCard title={state === "ok" ? "All set" : "Email verification"}>
      <p className={`text-sm ${state === "error" ? "text-red-400" : "text-slate-300"}`}>
        {msg}
      </p>
      {state === "ok" && (
        <Link to="/login" className={`${btnCls} mt-6 block text-center`}>
          Sign in
        </Link>
      )}
    </AuthCard>
  );
}
