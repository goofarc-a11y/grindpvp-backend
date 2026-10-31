const DEFAULT_API_BASE = "https://grindpvp-backend-1.onrender.com";
const API_BASE = (
  import.meta.env.VITE_API_BASE_URL || (import.meta.env.DEV ? "/api" : DEFAULT_API_BASE)
).replace(/\/+$/, "");

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

export async function api<T>(
  path: string,
  options: { method?: "GET" | "POST"; body?: unknown; token?: string; signal?: AbortSignal } = {},
): Promise<T> {
  const url = `${API_BASE}${path}`;
  if (url.startsWith("http://") && !/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?\//i.test(url)) {
    throw new Error("The GrindPvP API must use HTTPS outside local development.");
  }

  const headers = new Headers({ Accept: "application/json" });
  if (options.body !== undefined) headers.set("Content-Type", "application/json");
  if (options.token) headers.set("Authorization", `Bearer ${options.token}`);

  const response = await fetch(url, {
    method: options.method || "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: options.signal,
    credentials: "omit",
    cache: "no-store",
  });
  if (response.status === 204) return undefined as T;

  const raw = await response.text();
  let payload: unknown;
  try {
    payload = raw ? JSON.parse(raw) : {};
  } catch {
    throw new ApiError(`Backend returned an invalid response (HTTP ${response.status}).`, response.status);
  }

  if (!response.ok) {
    const detail =
      typeof payload === "object" && payload !== null && "detail" in payload
        ? (payload as { detail: unknown }).detail
        : undefined;
    throw new ApiError(
      typeof detail === "string" ? detail : `Backend request failed (HTTP ${response.status}).`,
      response.status,
    );
  }
  return payload as T;
}

export function query(values: Record<string, string | number | undefined>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined && value !== "") params.set(key, String(value));
  }
  return params.toString();
}
