/**
 * Backend URL resolution.
 *
 * Electron starts the backend on the first free port from 8000 and hands the
 * resulting URL to the page as a query parameter (?backendUrl=...), so the
 * renderer never has to guess. The Vite dev server proxies /api to :8000, so
 * outside Electron relative paths are used unless VITE_API_BASE_URL is set.
 */
function resolveBaseUrl(): string {
  const fromPage = new URLSearchParams(window.location.search).get("backendUrl");
  if (fromPage) return fromPage.replace(/\/$/, "");
  if (import.meta.env.VITE_API_BASE_URL) return import.meta.env.VITE_API_BASE_URL;
  return navigator.userAgent.includes("Electron") ? "http://127.0.0.1:8000" : "";
}

const BASE_URL = resolveBaseUrl();

/** Turn a non-2xx response into an Error carrying the backend's message. */
async function errorFromResponse(res: Response): Promise<Error> {
  const text = await res.text();
  try {
    const body = JSON.parse(text);
    const detail = body?.detail ?? body?.error;
    if (typeof detail === "string") return new Error(detail);
    if (detail) return new Error(JSON.stringify(detail));
  } catch {
    // not JSON
  }
  return new Error(`Request failed: ${res.status} ${text}`);
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await apiFetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  return (await res.json()) as T;
}

/**
 * fetch() against the backend. Resolves only for 2xx responses; any other
 * status throws an Error whose message is the backend's `detail`.
 */
async function apiFetch(path: string, options?: RequestInit): Promise<Response> {
  const fullPath = BASE_URL + (path.startsWith("/") ? path : `/${path}`);
  const res = await fetch(fullPath, options);
  if (!res.ok) throw await errorFromResponse(res);
  return res;
}

export { BASE_URL, request, apiFetch };
