import { describe, expect, it } from "vitest";
import { api, ApiError, errorMessage } from "@/api/client";
import { mockApi } from "@/test/utils";

describe("cliente da API", () => {
  it("envia o token e serializa JSON", async () => {
    const { fetchMock } = mockApi({ "POST /api/tasks": (b: unknown) => ({ status: 201, body: { echo: b } }) });
    const r = await api.post<{ echo: unknown }>("/api/tasks", { title: "x" });
    expect(r.echo).toEqual({ title: "x" });
    const init = fetchMock.mock.calls[0]![1] as RequestInit;
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer t");
  });

  it("converte erros do backend em ApiError com campos", async () => {
    mockApi({ "POST /api/projects": { status: 422, body: { error: { code: "validation_failed", message: "Dados inválidos.", details: { errors: [{ field: "name", message: "obrigatório" }] } } } } });
    const e = await api.post("/api/projects", {}).catch((x: unknown) => x);
    expect(e).toBeInstanceOf(ApiError);
    expect((e as ApiError).fieldErrors[0]!.field).toBe("name");
    expect(errorMessage(e)).toContain("name: obrigatório");
  });

  it("identifica operações que exigem confirmação (428)", async () => {
    mockApi({ "DELETE /api/projects/p1": { status: 428, body: { error: { code: "confirmation_required", message: "Confirme." } } } });
    const e = (await api.del("/api/projects/p1").catch((x: unknown) => x)) as ApiError;
    expect(e.needsConfirmation).toBe(true);
  });

  it("reporta falha de ligação de forma compreensível", async () => {
    mockApi({});
    (globalThis.fetch as unknown as { mockImplementationOnce: (f: () => never) => void }).mockImplementationOnce(() => {
      throw new TypeError("Failed to fetch");
    });
    const e = (await api.get("/api/x").catch((x: unknown) => x)) as ApiError;
    expect(e.code).toBe("network_error");
    expect(e.message).toMatch(/backend local/);
  });
});
