/**
 * Cliente HTTP do backend local.
 *
 * - Em Tauri: o processo nativo lança o backend e devolve `{ baseUrl, token }` via `invoke`.
 * - No browser (desenvolvimento): pedidos relativos `/api`, com o token injectado pelo proxy do Vite.
 */

export interface BackendConfig {
  baseUrl: string;
  token: string | null;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }

  get fieldErrors(): { field: string; message: string }[] {
    const errs = this.details.errors;
    return Array.isArray(errs) ? (errs as { field: string; message: string }[]) : [];
  }

  get needsConfirmation(): boolean {
    return this.status === 428;
  }
}

let configPromise: Promise<BackendConfig> | null = null;

export function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

async function loadConfig(): Promise<BackendConfig> {
  if (isTauri()) {
    const { invoke } = await import("@tauri-apps/api/core");
    return invoke<BackendConfig>("backend_config");
  }
  return { baseUrl: "", token: null };
}

export function getBackendConfig(): Promise<BackendConfig> {
  configPromise ??= loadConfig().catch((e: unknown) => {
    configPromise = null;
    throw e;
  });
  return configPromise;
}

/** Apenas para testes. */
export function setBackendConfig(cfg: BackendConfig): void {
  configPromise = Promise.resolve(cfg);
}

type Query = Record<string, string | number | boolean | string[] | null | undefined>;

function buildQuery(q?: Query): string {
  if (!q) return "";
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => p.append(k, x));
    else p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

export interface RequestOptions {
  method?: string;
  body?: unknown;
  query?: Query;
  signal?: AbortSignal;
  raw?: boolean;
}

export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const cfg = await getBackendConfig();
  const headers: Record<string, string> = {};
  if (cfg.token) headers.Authorization = `Bearer ${cfg.token}`;
  let body: BodyInit | undefined;
  if (opts.body instanceof FormData) body = opts.body;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  let res: Response;
  try {
    res = await fetch(`${cfg.baseUrl}${path}${buildQuery(opts.query)}`, {
      method: opts.method ?? (body ? "POST" : "GET"),
      headers,
      body,
      signal: opts.signal,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(0, "network_error", "Sem ligação ao backend local. Verifique se o serviço está a correr.");
  }
  if (opts.raw) return res as unknown as T;
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  const data: unknown = text ? safeJson(text) : null;
  if (!res.ok) {
    const err = (data as { error?: { code?: string; message?: string; details?: Record<string, unknown> } } | null)
      ?.error;
    throw new ApiError(res.status, err?.code ?? "http_error", err?.message ?? `Erro ${res.status}`, err?.details ?? {});
  }
  return data as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return { error: { code: "invalid_response", message: "Resposta inválida do backend." } };
  }
}

export const api = {
  get: <T>(path: string, query?: Query) => request<T>(path, { query }),
  post: <T>(path: string, body?: unknown, query?: Query) => request<T>(path, { method: "POST", body: body ?? {}, query }),
  put: <T>(path: string, body?: unknown) => request<T>(path, { method: "PUT", body: body ?? {} }),
  patch: <T>(path: string, body?: unknown) => request<T>(path, { method: "PATCH", body: body ?? {} }),
  del: <T = void>(path: string, query?: Query) => request<T>(path, { method: "DELETE", query }),
};

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    const fields = e.fieldErrors.map((f) => (f.field ? `${f.field}: ${f.message}` : f.message));
    return fields.length ? `${e.message} ${fields.join("; ")}` : e.message;
  }
  if (e instanceof Error) return e.message;
  return "Erro desconhecido.";
}
