// Single place that knows how to reach the Eden local backend. Same-origin in
// production (FastAPI serves both the API and this built app); in dev, set
// VITE_API_BASE to point at "eden_local" running separately.
const BASE = import.meta.env.VITE_API_BASE ?? "";

// Surface the backend's error detail (FastAPI puts it in {"detail": ...}) instead of just the status code.
async function fail(method: string, path: string, r: Response): Promise<never> {
  let detail = "";
  try {
    const j = await r.json();
    detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? "");
  } catch {
    /* body was not JSON */
  }
  throw new Error(`${method} ${path} -> ${r.status}${detail ? `: ${detail}` : ""}`);
}

export async function apiGet<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}/api${path}`);
  if (!r.ok) return fail("GET", path, r);
  return r.json();
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${BASE}/api${path}`, {
    method: "POST",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) return fail("POST", path, r);
  return r.json();
}

export async function apiDelete<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE}/api${path}`, { method: "DELETE" });
  if (!r.ok) return fail("DELETE", path, r);
  return r.json();
}
