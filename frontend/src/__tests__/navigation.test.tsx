import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { AppRoutes } from "@/App";
import { emptyDashboard, mockApi, renderApp, task } from "@/test/utils";

const base = {
  "GET /health": { status: "ok", version: "0.1.0" },
  "GET /api/settings": { reduced_motion: false },
  "GET /api/notifications": [],
  "GET /api/dashboard": emptyDashboard,
  "GET /api/projects": { items: [], total: 0, limit: 100, offset: 0 },
  "GET /api/tasks": { items: [task()], total: 1, limit: 200, offset: 0 },
};

describe("navegação e pesquisa global", () => {
  it("navega pela barra lateral", async () => {
    mockApi(base);
    renderApp(<AppRoutes />);
    const nav = screen.getByRole("navigation", { name: "Navegação principal" });
    await userEvent.click(within(nav).getByRole("link", { name: /Tarefas/ }));
    // Páginas carregadas sob pedido (lazy): em hardware lento o primeiro carregamento demora mais.
    expect(await screen.findByRole("heading", { name: "Tarefas" }, { timeout: 8000 })).toBeInTheDocument();
    expect(await screen.findByText("Escrever testes")).toBeInTheDocument();
  }, 40_000);

  it("abre a Command Palette com ⌘K e mostra resultados da pesquisa", async () => {
    mockApi({
      ...base,
      "GET /api/search": (_b: unknown, url: URL) => ({
        engine: "fts5",
        query: url.searchParams.get("q"),
        hits: [{ entity_type: "note", entity_id: "n1", title: "Decisão JWT", snippet: "tokens [curtos]", route: "/notes/n1" }],
      }),
    });
    renderApp(<AppRoutes />);
    await userEvent.keyboard("{Meta>}k{/Meta}");
    const input = await screen.findByPlaceholderText(/Pesquisar ou escrever/);
    await userEvent.type(input, "jwt");
    expect(await screen.findByText("Decisão JWT")).toBeInTheDocument();
    expect(screen.getByText(/Criar tarefa «jwt»/)).toBeInTheDocument();
  });

  it("executa um comando local e mostra o resultado", async () => {
    const { calls } = mockApi({ ...base, "POST /api/commands": { kind: "created", message: "Tarefa criada: Ler RFC", route: "/tasks/t9", entity_type: "task", entity_id: "t9" } });
    renderApp(<AppRoutes />);
    await userEvent.type(screen.getByLabelText("Barra de comando"), "tarefa Ler RFC{Enter}");
    expect(await screen.findByText("Tarefa criada: Ler RFC")).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/commands")!.body).toEqual({ text: "tarefa Ler RFC" });
  });

  it("indica quando o backend está offline", async () => {
    mockApi({ ...base, "GET /health": { status: 503, body: { error: { code: "x", message: "down" } } } });
    renderApp(<AppRoutes />);
    expect(await screen.findByText(/O backend local não está a responder/, {}, { timeout: 4000 })).toBeInTheDocument();
  });
});
