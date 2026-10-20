import { clearSession, getSession } from "./session";

/** Empty = same origin (FastAPI serves the UI). Set VITE_API_BASE when the API lives elsewhere. */
const base = (): string => (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  readonly status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export const isUnauthorized = (e: unknown): boolean => e instanceof ApiError && e.status === 401;

export interface RequestOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
  /** Do not attach the session token (public endpoints). */
  anonymous?: boolean;
}

async function send(path: string, options: RequestOptions): Promise<Response> {
  const headers: Record<string, string> = { ...(options.headers ?? {}) };
  const session = getSession();
  if (session?.token && !options.anonymous) headers.Authorization = "Bearer " + session.token;
  let body: BodyInit | undefined;
  if (options.body !== undefined) {
    if (options.body instanceof FormData) body = options.body;
    else {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(options.body);
    }
  }
  let response: Response;
  try {
    response = await fetch(base() + path, { method: options.method ?? (body === undefined ? "GET" : "POST"), headers, body });
  } catch {
    throw new ApiError(0, "The CashBridge server is not reachable. Start it with `make run`, or check VITE_API_BASE.");
  }
  if (response.status === 401 && session && !options.anonymous) clearSession();
  return response;
}

async function errorText(response: Response): Promise<string> {
  try {
    const d = await response.json();
    return typeof d.detail === "string" ? d.detail : response.statusText;
  } catch {
    return response.statusText;
  }
}

export async function request<T = unknown>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await send(path, options);
  const text = await response.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { detail: text };
  }
  if (!response.ok) {
    const d = data as { detail?: unknown; error?: string } | null;
    const detail = d?.detail;
    const message =
      typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map((x: { msg: string }) => x.msg).join("; ") : d?.error || response.statusText;
    throw new ApiError(response.status, message || "Request failed");
  }
  return data as T;
}

export const get = <T>(path: string, options?: RequestOptions): Promise<T> => request<T>(path, options);

export const post = <T>(path: string, body?: unknown, options?: RequestOptions): Promise<T> =>
  request<T>(path, { ...options, method: "POST", body: body === undefined ? {} : body });

/** Fetch a file with the session token and hand it to the browser as a download. */
export async function download(path: string, filename: string, options: RequestOptions = {}): Promise<void> {
  const response = await send(path, options);
  if (!response.ok) throw new ApiError(response.status, await errorText(response));
  const url = URL.createObjectURL(await response.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
