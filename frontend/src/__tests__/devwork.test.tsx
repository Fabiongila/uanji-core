import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { CommandPalette } from "@/components/layout/CommandPalette";
import { AIProviderPanel } from "@/features/AIProvider";
import { ProjectCode } from "@/features/DevWork";
import { PerformanceCenter } from "@/features/PerformanceCenter";
import type { AppSettings } from "@/api/types";
import { mockApi, renderApp } from "@/test/utils";

const week = (label: string, done: number) => ({ week: label, label, done, created: 2, cycle_avg_h: 30, blocked_h: 1, focus_h: 3, interruptions: 1, switches_per_hour: null });

describe("Centro de desempenho", () => {
  it("mostra tempo de ciclo, bloqueios, interrupções, objectivos e evolução semanal", async () => {
    mockApi({
      "GET /api/projects": { items: [], total: 0 },
      "GET /api/performance": {
        cycle_time: { count: 4, avg_h: 30, median_h: 20, p85_h: 50 },
        lead_time: { count: 4, avg_h: 72, median_h: 60, p85_h: 90 },
        cycle_missing: 1,
        blocked: { now: 1, items: [{ id: "t1", number: 7, title: "Integração com o hospital", reason: "À espera de credenciais", hours: 49 }], total_hours_in_done: 3 },
        interruptions: { short_focus: 3, focus_sessions: 9, regressions: 2, per_day: 0.9, app_switches_per_hour: 14.2, monitor_data: true },
        goals: [{ id: "g1", title: "API pública v1", description: "", project_id: null, project_name: null, target_date: "2026-12-01", status: "active", tasks_total: 4, tasks_done: 3, percent: 75 }],
        weekly: [week("12/10", 2), week("19/10", 3)],
        trend: { done_delta: 1, cycle_delta_h: -4 },
        sources: { cycle_time: "Início → fim.", interruptions: "Focos curtos." },
      },
    });
    renderApp(<PerformanceCenter />);
    expect(await screen.findByText("30,0 h")).toBeInTheDocument();
    expect(screen.getByText("Integração com o hospital")).toBeInTheDocument();
    expect(screen.getByText("UJ-7")).toBeInTheDocument();
    expect(screen.getByText("2,0 d")).toBeInTheDocument(); // 49 h bloqueada
    expect(screen.getByText("75% · 3/4")).toBeInTheDocument();
    expect(screen.getByText("14,2")).toBeInTheDocument();
    expect(screen.getByText(/1 tarefa\(s\) concluída\(s\) a mais/)).toBeInTheDocument();
  });
});

describe("Integração com desenvolvimento", () => {
  it("mostra commits, PRs e issues com as tarefas ligadas e sincroniza", async () => {
    const t = { id: "t1", ref: "UJ-1", title: "Login", status: "in_progress" };
    const { calls } = mockApi({
      "GET /api/projects/p1/code": {
        ref_hint: "Escreva UJ-<número>.",
        repos: [{
          repo: "foo/q360", url: "https://github.com/foo/q360",
          commits: [{ sha: "a3f9c21", message: "fix login UJ-1", author: "F", date: null, url: "u", tasks: [t] }],
          branches: [{ name: "main", sha: "a3f", tasks: [] }],
          pulls: [{ number: 12, title: "Auth JWT", state: "merged", branch: "auth", author: "f", url: "pr", date: null, tasks: [t] }],
          issues: [], releases: [],
        }],
      },
      "POST /api/projects/p1/code/sync": { new_links: 2, repos: ["foo/q360"], errors: [] },
    });
    renderApp(<ProjectCode projectId="p1" />);
    const repo = await screen.findByRole("region", { name: "Repositório foo/q360" });
    expect(within(repo).getByText("fix login UJ-1")).toBeInTheDocument();
    expect(within(repo).getByRole("link", { name: "UJ-1" })).toHaveAttribute("href", "/tasks/t1");
    await userEvent.click(screen.getByRole("tab", { name: "Pull requests" }));
    expect(within(repo).getByText("Auth JWT")).toBeInTheDocument();
    expect(within(repo).getByText("integrado")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Ligar código às tarefas" }));
    expect(calls.some((c) => c.path === "/api/projects/p1/code/sync")).toBe(true);
  });
});

describe("Command Palette", () => {
  it("procura ficheiros, executa fluxos e pede ao assistente", async () => {
    const { calls } = mockApi({
      "GET /api/search": { hits: [], engine: "fts5" },
      "GET /api/automations": [{ id: "a1", name: "Deploy de teste", enabled: true }],
      "GET /api/palette/files": { files: [{ path: "/u/q360/src/api/pagination.py", relative: "src/api/pagination.py", root: "q360" }] },
      "POST /api/palette/open-file": { opened: "/u/q360/src/api/pagination.py", with: "Visual Studio Code" },
      "POST /api/automations/a1/run": { id: "r1", status: "success", error: "" },
    });
    renderApp(<CommandPalette open onClose={() => undefined} />);
    await userEvent.type(screen.getByPlaceholderText("Pesquisar ou escrever uma acção…"), "pag");
    await userEvent.click(await screen.findByText("src/api/pagination.py"));
    expect(calls.find((c) => c.path === "/api/palette/open-file")?.body).toEqual({ path: "/u/q360/src/api/pagination.py" });
    expect(screen.getByText("Pedir ao UANJI: «pag»")).toBeInTheDocument();
    await userEvent.clear(screen.getByPlaceholderText("Pesquisar ou escrever uma acção…"));
    await userEvent.type(screen.getByPlaceholderText("Pesquisar ou escrever uma acção…"), "deploy");
    await userEvent.click(await screen.findByText("Executar «Deploy de teste»"));
    expect(calls.some((c) => c.path === "/api/automations/a1/run")).toBe(true);
  });
});

describe("Modelo de IA próprio", () => {
  it("configura um servidor compatível com OpenAI e testa a ligação", async () => {
    const settings = { assistant: { provider: "none", model: "", base_url: "", secret_id: null, confirm_creates: false, confirm_updates: true, history_days: 30, context_turns: 12 } } as unknown as AppSettings;
    const { calls } = mockApi({
      "PATCH /api/settings": (body: unknown) => body,
      "POST /api/assistant/test": { ok: true, reply: "OK", models: ["qwen2.5:7b"], model_found: true },
    });
    function Host() {
      const [s, setS] = useState(settings);
      return <AIProviderPanel settings={s} setSettings={setS} vault={[]} />;
    }
    renderApp(<Host />);
    await userEvent.selectOptions(screen.getByLabelText("Fornecedor"), "openai_compatible");
    await userEvent.click(screen.getByRole("button", { name: "Ollama (local)" }));
    await userEvent.type(screen.getByLabelText("Modelo"), "qwen2.5:7b");
    expect(screen.getByText(/as conversas não saem deste Mac/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Guardar e testar ligação" }));
    expect(await screen.findByText(/Ligação a funcionar/)).toBeInTheDocument();
    const patch = calls.find((c) => c.method === "PATCH")?.body as { values: { assistant: { provider: string; base_url: string } } };
    expect(patch.values.assistant).toMatchObject({ provider: "openai_compatible", base_url: "http://localhost:11434/v1" });
  });
});
