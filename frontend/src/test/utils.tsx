import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import { setBackendConfig } from "@/api/client";

type Handler = (body: unknown, url: URL) => { status?: number; body?: unknown } | unknown;
export type Routes = Record<string, Handler | unknown>;

/** Substitui `fetch` por um router simples: chaves "MÉTODO /caminho" (sem query). */
export function mockApi(routes: Routes) {
  setBackendConfig({ baseUrl: "http://test", token: "t" });
  const calls: { method: string; path: string; body: unknown; url: URL }[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    const method = (init?.method ?? "GET").toUpperCase();
    const body = typeof init?.body === "string" ? JSON.parse(init.body) : init?.body;
    calls.push({ method, path: url.pathname, body, url });
    const key = `${method} ${url.pathname}`;
    if (!(key in routes)) return new Response(JSON.stringify({ error: { code: "not_found", message: `sem mock: ${key}` } }), { status: 404 });
    const h = routes[key];
    const out = typeof h === "function" ? (h as Handler)(body, url) : h;
    const res = out && typeof out === "object" && "status" in (out as object) && "body" in (out as object) ? (out as { status: number; body: unknown }) : { status: 200, body: out };
    return new Response(res.status === 204 ? null : JSON.stringify(res.body), { status: res.status ?? 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}

export function renderApp(ui: ReactElement, { route = "/" }: { route?: string } = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

export const emptyDashboard = {
  generated_at: "2026-10-24T10:00:00Z",
  is_empty: true,
  counters: { active_projects: 0, blocked_projects: 0, pending_tasks: 0, overdue_tasks: 0, done_today: 0, done_week: 0, focus_minutes_today: 0, focus_minutes_week: 0, automations_running: 0, unread_notifications: 0 },
  active_projects: [],
  priority_tasks: [],
  upcoming: [],
  recent_activity: [],
  alerts: [],
  trend: [],
  focus_active: null,
};

export function task(over: Record<string, unknown> = {}) {
  return {
    id: "t1", title: "Escrever testes", description: "", project_id: "p1", parent_id: null, status: "todo", priority: "high",
    due_at: null, estimate_minutes: null, completion_criteria: "", blocked_reason: "", notes: "", position: 0,
    completed_at: null, archived_at: null, postponed_count: 0, created_at: "2026-10-24T10:00:00Z", updated_at: "2026-10-24T10:00:00Z",
    overdue: false, subtasks_total: 0, subtasks_done: 0, project_name: "UANJI", depends_on: [], blocked_by_open: 0, ...over,
  };
}
