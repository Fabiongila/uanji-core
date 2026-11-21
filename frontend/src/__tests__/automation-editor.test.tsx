import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import AutomationEditorPage from "@/pages/AutomationEditor";
import { mockApi, renderApp } from "@/test/utils";

const catalog = [
  {
    name: "notify", label: "Mostrar notificação", description: "Cria uma notificação interna.", mutates: false, reversible: false,
    schema: { properties: { title: { type: "string", title: "Title" }, body: { type: "string", title: "Body", default: "" }, level: { enum: ["info", "warning", "error"], type: "string", default: "info" } }, required: ["title"] },
  },
];

function setup(validate: unknown) {
  return mockApi({
    "GET /api/automations/actions": catalog,
    "GET /api/projects": { items: [], total: 0, limit: 100, offset: 0 },
    "POST /api/automations/validate": validate,
    "POST /api/automations": (b: unknown) => ({ status: 201, body: { id: "a1", version: 1, ...(b as object), definition: (b as { definition: unknown }).definition, last_run: null, run_counts: {} } }),
  });
}

describe("construtor visual de automações", () => {
  it("adiciona uma acção, valida no backend e guarda a definição sequencial", async () => {
    const { calls } = setup({ valid: true, errors: [] });
    renderApp(<Routes><Route path="/automations/:id" element={<AutomationEditorPage />} /></Routes>, { route: "/automations/new" });
    await userEvent.click(await screen.findByRole("button", { name: /Mostrar notificação/ }));
    await userEvent.type(await screen.findByLabelText("Title *"), "Olá {{{{trigger.title}}");  // userEvent: "{{" escreve "{"
    await userEvent.click(screen.getByRole("button", { name: /Validar e guardar/ }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/api/automations")).toBe(true));
    const saved = calls.find((c) => c.path === "/api/automations")!.body as { definition: { steps: { id: string; action: string; params: Record<string, unknown> }[] } };
    expect(saved.definition.steps).toEqual([{ id: "s1", action: "notify", params: { body: "", level: "info", title: "Olá {{trigger.title}}" } }]);
  });

  it("mostra erros de validação e não guarda", async () => {
    const { calls } = setup({ valid: false, errors: [{ path: "steps.0.params.title", message: "Field required", step: "s1" }] });
    renderApp(<Routes><Route path="/automations/:id" element={<AutomationEditorPage />} /></Routes>, { route: "/automations/new" });
    await userEvent.click(await screen.findByRole("button", { name: /Mostrar notificação/ }));
    await userEvent.click(screen.getByRole("button", { name: /Validar e guardar/ }));
    expect(await screen.findByText(/steps.0.params.title: Field required/)).toBeInTheDocument();
    expect(calls.some((c) => c.path === "/api/automations")).toBe(false);
  });

  it("recusa guardar um fluxo sem acções", async () => {
    const { calls } = setup({ valid: true, errors: [] });
    renderApp(<Routes><Route path="/automations/:id" element={<AutomationEditorPage />} /></Routes>, { route: "/automations/new" });
    await screen.findByRole("button", { name: /Mostrar notificação/ });
    await userEvent.click(screen.getByRole("button", { name: /Validar e guardar/ }));
    expect(await screen.findByText(/pelo menos uma acção/)).toBeInTheDocument();
    expect(calls.some((c) => c.path === "/api/automations/validate")).toBe(false);
  });
});
