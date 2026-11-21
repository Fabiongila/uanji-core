import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ProjectFormDialog, TaskFormDialog } from "@/features/forms";
import { mockApi, renderApp, task } from "@/test/utils";

const projects = { "GET /api/projects": { items: [{ id: "p1", name: "UANJI" }], total: 1, limit: 100, offset: 0 } };

describe("formulários", () => {
  it("valida o título da tarefa antes de enviar", async () => {
    const { calls } = mockApi(projects);
    renderApp(<TaskFormDialog open onClose={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: "Guardar" }));
    expect(await screen.findByText("O título é obrigatório.")).toBeInTheDocument();
    expect(calls.filter((c) => c.method === "POST")).toHaveLength(0);
  });

  it("exige motivo quando a tarefa fica bloqueada", async () => {
    mockApi(projects);
    renderApp(<TaskFormDialog open onClose={() => {}} />);
    await userEvent.type(screen.getByLabelText("Título"), "Deploy");
    await userEvent.selectOptions(screen.getByLabelText("Estado"), "blocked");
    await userEvent.click(screen.getByRole("button", { name: "Guardar" }));
    expect(await screen.findByText("Indique o motivo do bloqueio.")).toBeInTheDocument();
  });

  it("cria uma tarefa com o projecto e prazo convertido para ISO", async () => {
    const onClose = vi.fn();
    const { calls } = mockApi({ ...projects, "POST /api/tasks": (b: unknown) => ({ status: 201, body: task(b as Record<string, unknown>) }) });
    renderApp(<TaskFormDialog open onClose={onClose} defaults={{ project_id: "p1" }} />);
    await screen.findByRole("option", { name: "UANJI" });
    await userEvent.type(screen.getByLabelText("Título"), "Nova tarefa");
    await userEvent.type(screen.getByLabelText(/Prazo/), "2026-11-02T14:30");
    await userEvent.click(screen.getByRole("button", { name: "Guardar" }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    const post = calls.find((c) => c.method === "POST")!;
    expect(post.body).toMatchObject({ title: "Nova tarefa", project_id: "p1", status: "todo" });
    expect((post.body as { due_at: string }).due_at).toMatch(/^2026-11-02T\d\d:30:00\.000Z$/);
  });

  it("edita um projecto e mostra erros de campo devolvidos pelo backend", async () => {
    mockApi({
      "PATCH /api/projects/p1": { status: 422, body: { error: { code: "validation_failed", message: "Dados inválidos.", details: { errors: [{ field: "name", message: "Nome já usado" }] } } } },
    });
    const project = { id: "p1", name: "UANJI", description: "", category: "", status: "active", priority: "medium", start_date: null, due_date: null, objectives: "", expected_results: "", blocked_reason: "" };
    renderApp(<ProjectFormDialog open onClose={() => {}} project={project as never} />);
    await userEvent.click(screen.getByRole("button", { name: "Guardar" }));
    expect(await screen.findByText("Nome já usado")).toBeInTheDocument();
  });
});
