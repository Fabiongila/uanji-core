import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import DashboardPage from "@/pages/Dashboard";
import { emptyDashboard, mockApi, renderApp, task } from "@/test/utils";

const health = { "GET /health": { status: "ok", version: "0.1.0" }, "GET /api/projects": { items: [], total: 0, limit: 100, offset: 0 } };

describe("Dashboard", () => {
  it("mostra estado de carregamento e depois o estado vazio com acção", async () => {
    mockApi({ ...health, "GET /api/dashboard": emptyDashboard });
    renderApp(<DashboardPage />);
    expect(screen.getByRole("status")).toHaveTextContent(/A carregar/);
    expect(await screen.findByText("O centro de comando está vazio")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Criar primeiro projecto" })).toBeInTheDocument();
  });

  it("mostra indicadores e tarefas reais", async () => {
    mockApi({
      ...health,
      "GET /api/dashboard": {
        ...emptyDashboard,
        is_empty: false,
        counters: { ...emptyDashboard.counters, pending_tasks: 7, overdue_tasks: 2 },
        priority_tasks: [task({ title: "Rever PR", overdue: true, due_at: "2026-10-20T10:00:00Z" })],
        alerts: [{ level: "warning", title: "2 tarefa(s) atrasada(s)", link: "/tasks?due=overdue" }],
      },
    });
    renderApp(<DashboardPage />);
    expect(await screen.findByText("Rever PR")).toBeInTheDocument();
    expect(screen.getByText("2 tarefa(s) atrasada(s)")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
  });

  it("mostra erro compreensível e permite tentar novamente", async () => {
    mockApi({ ...health, "GET /api/dashboard": { status: 500, body: { error: { code: "internal_error", message: "Erro interno do servidor." } } } });
    renderApp(<DashboardPage />);
    expect(await screen.findByText("Erro interno do servidor.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Tentar novamente/ })).toBeInTheDocument();
  });
});
