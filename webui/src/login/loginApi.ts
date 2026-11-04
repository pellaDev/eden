import { translate as t } from "../lib/i18n";

// The three calls the login app makes to eden_remote. Everything lives under /eden/ (the prefix eden_remote owns).
export type Appearance = { theme: "light" | "dark" | null; field_style: "fill" | "outline" | null };
export type AppState = { mode: "login" | "enroll" | "closed" | "home"; remaining: number; language?: string; appearance: Appearance };

// A refusal from eden_remote: the HTTP status, its short error code and, for a lockout, the seconds left.
export class ApiError extends Error {
  constructor(public status: number, public code: string, public retryAfter = 0) {
    super(code);
  }
}

async function request<T>(method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
  const r = await fetch(`/eden${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store",
    credentials: "same-origin",
  });
  let data: { error?: string; retry_after?: number } | null = null;
  try {
    data = await r.json();
  } catch {
    /* body was not JSON */
  }
  if (!r.ok) throw new ApiError(r.status, data?.error ?? "unknown", data?.retry_after ?? 0);
  return data as T;
}

export type HomeService = { name: string; port: number; note: string; avatar: string | null };
export type HomeData = {
  host_name: string;
  device: { name: string; known: boolean; enabled: boolean } | null;
  trusted: boolean;
  services: HomeService[];
};
export const getHome = () => request<HomeData>("GET", "/api/home");
export const getState = () => request<AppState>("GET", "/api/state");
export const postLogin = (password: string, totp: string) => request<{ ok: true; next: string }>("POST", "/api/login", { password, totp });
export const postEnroll = (password: string, totp: string) => request<{ ok: true }>("POST", "/api/enroll", { password, totp });

const minutes = (seconds: number) => Math.max(1, Math.ceil(seconds / 60));

// What the person reads for each way a request can fail (the server never says which factor was wrong).
export function errorText(err: unknown, what: "login" | "enroll"): string {
  if (err instanceof ApiError) {
    if (err.status === 429) return minutes(err.retryAfter) === 1 ? t("login.tooMany1") : t("login.tooManyN", { n: minutes(err.retryAfter) });
    if (err.status === 401) return t("login.invalid");
    if (err.code === "bad_code") return t("login.badCode");
    if (err.status === 503) return t("login.unavailable");
    if (err.status === 409 || err.status === 403) return t("login.changed");
    return what === "login" ? t("login.loginFailed") : t("login.enrollFailed");
  }
  return t("login.unreachable");
}
