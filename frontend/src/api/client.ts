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
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
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
    const detail =
      (data && (data.detail || data.message)) || res.statusText || "Request failed";
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
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
  provider: string | null;
  error: string | null;
  created_at: string;
  finished_at: string | null;
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
  validation?: Validation | null;
  created_at?: string | null;
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

  deleteAccount: () => request<void>("/me", { method: "DELETE", auth: true }),

  // ── plans ──────────────────────────────────────────────────────────────────

  listPlans: () => request<Job[]>("/plans", { auth: true }),

  getPlan: (id: string) => request<Plan>(`/plans/${id}`, { auth: true }),

  planStatus: (id: string) => request<Job>(`/plans/${id}/status`, { auth: true }),

  deletePlan: (id: string) =>
    request<void>(`/plans/${id}`, { method: "DELETE", auth: true }),

  createPlan: (files: { transcript: File; handbook: File; career: File; cv?: File | null }, constraints: Constraints) => {
    const fd = new FormData();
    fd.append("transcript", files.transcript);
    fd.append("handbook", files.handbook);
    fd.append("career", files.career);
    if (files.cv) fd.append("cv", files.cv);
    fd.append("constraints", JSON.stringify(constraints));
    return request<Job>("/plans", { method: "POST", auth: true, body: fd });
  },
};
