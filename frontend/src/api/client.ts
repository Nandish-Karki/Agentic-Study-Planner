// Thin typed client for the FastAPI backend (study_planner.api).
// Base URL from VITE_API_URL; token kept in localStorage.

const BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const TOKEN_KEY = "sp_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(t: string | null) {
  if (t) localStorage.setItem(TOKEN_KEY, t);
  else localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  detail: unknown; // raw `detail` (may be a structured object, e.g. quota info)
  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
  // Convenience: structured detail for a quota-exhausted 429, else null.
  get quota(): { reason: string; message: string; retry_after_s?: number; retry_at?: string } | null {
    const d = this.detail as { reason?: string } | undefined;
    if (d && typeof d === "object" && (d.reason === "quota_exhausted" || d.reason === "daily_user_limit")) {
      return d as { reason: string; message: string; retry_after_s?: number; retry_at?: string };
    }
    return null;
  }
}

async function request<T>(
  path: string,
  opts: RequestInit & { auth?: boolean } = {},
): Promise<T> {
  const headers = new Headers(opts.headers);
  if (opts.auth) {
    const t = getToken();
    if (t) headers.set("Authorization", `Bearer ${t}`);
  }
  const res = await fetch(`${BASE}${path}`, { ...opts, headers });
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  const data = text ? JSON.parse(text) : undefined;
  if (!res.ok) {
    const raw = (data && (data.detail ?? data.message)) ?? res.statusText ?? "Request failed";
    const message =
      typeof raw === "string" ? raw : (raw && raw.message) || JSON.stringify(raw);
    throw new ApiError(res.status, message, raw);
  }
  return data as T;
}

// ── types ────────────────────────────────────────────────────────────────────

export interface User {
  id: string;
  email: string;
  is_verified: boolean;
  created_at: string;
}

export interface Job {
  id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  phase: string | null; // live progress label while running
  provider: string | null;
  error: string | null;
  failure_reason: string | null; // e.g. "quota_exhausted"
  retry_at: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface ServiceStatus {
  quota_available: boolean;
  retry_at: string | null;
  cooldown_seconds: number;
}

export interface Finding {
  rule: string;
  message: string;
}

export interface Validation {
  ok: boolean;
  errors: Finding[];
  warnings: Finding[];
  stats: Record<string, unknown>;
}

export interface Plan {
  job_id: string;
  status: string;
  study_plan_md?: string;
  skill_gaps_md?: string;
  profile_md?: string;
  module_catalog_md?: string;
  validation?: Validation | null;
  created_at?: string | null;
}

export interface GuestJob {
  job: Job;
  guest_token: string;
}

export interface Constraints {
  degree_type: string;
  target_semesters: number;
  default_cp_per_semester?: number | null;
  cp_overrides?: Record<number, number>;
}

// ── auth ─────────────────────────────────────────────────────────────────────

export const api = {
  signup: (email: string, password: string) =>
    request<{ id: string; email: string; message: string; verify_token?: string }>(
      "/auth/signup",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          password,
          accept_privacy: true,
          accept_tos: true,
        }),
      },
    ),

  verify: (token: string) =>
    request<{ message: string }>(`/auth/verify?token=${encodeURIComponent(token)}`, {
      method: "POST",
    }),

  resendVerification: (email: string) =>
    request<{ message: string; verify_token?: string }>("/auth/resend-verification", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    }),

  login: (email: string, password: string) =>
    request<{ access_token: string }>("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    }),

  resetRequest: (email: string) =>
    request<{ message: string; reset_token?: string }>("/auth/password-reset/request", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    }),

  resetConfirm: (token: string, new_password: string) =>
    request<{ message: string }>("/auth/password-reset/confirm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, new_password }),
    }),

  me: () => request<User>("/auth/me", { auth: true }),

  status: () => request<ServiceStatus>("/status"),

  deleteAccount: () => request<void>("/me", { method: "DELETE", auth: true }),

  // ── plans ──────────────────────────────────────────────────────────────────

  listPlans: () => request<Job[]>("/plans", { auth: true }),

  getPlan: (id: string) => request<Plan>(`/plans/${id}`, { auth: true }),

  planStatus: (id: string) => request<Job>(`/plans/${id}/status`, { auth: true }),

  deletePlan: (id: string) =>
    request<void>(`/plans/${id}`, { method: "DELETE", auth: true }),

  createPlan: (
    files: { handbook: File; career: File; transcript?: File | null; cv?: File | null },
    opts?: { newStudent?: boolean; constraints?: Constraints },
  ) => {
    const fd = new FormData();
    fd.append("handbook", files.handbook);
    fd.append("career", files.career);
    // A new first-semester student uploads no transcript; the API synthesizes a
    // blank 0-CP one. A continuing student must provide it.
    if (files.transcript) fd.append("transcript", files.transcript);
    if (files.cv) fd.append("cv", files.cv);
    if (opts?.newStudent) fd.append("new_student", "true");
    // The preferences UI was removed; the API defaults every constraint
    // server-side (degree=master, target_semesters=4, no CP cap) when omitted.
    if (opts?.constraints) fd.append("constraints", JSON.stringify(opts.constraints));
    return request<Job>("/plans", { method: "POST", auth: true, body: fd });
  },

  // One-click demo on the bundled sample student (no upload needed).
  createDemoPlan: (role = "data_engineer") =>
    request<Job>("/plans/demo", {
      method: "POST", auth: true,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role }),
    }),

  // ── guest demo (no login) ────────────────────────────────────────────────
  // Run the bundled demo without an account. Returns the job + a short-lived
  // token used to poll status and fetch the result.
  createGuestDemoPlan: (role = "data_engineer") =>
    request<GuestJob>("/plans/demo/public", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role }),
    }),

  guestPlanStatus: (id: string, token: string) =>
    request<Job>(`/plans/public/${id}/status?token=${encodeURIComponent(token)}`),

  getGuestPlan: (id: string, token: string) =>
    request<Plan>(`/plans/public/${id}?token=${encodeURIComponent(token)}`),
};
