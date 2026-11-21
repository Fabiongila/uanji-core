import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { mockApi, renderApp } from "@/test/utils";

function Broken(): never {
  throw new Error("Attempted to assign to readonly property.");
}

describe("ErrorBoundary", () => {
  it("mostra o erro em vez de um ecrã vazio e regista-o no backend", async () => {
    const { calls } = mockApi({ "POST /api/diagnostics/client-error": { ok: true } });
    const spy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    renderApp(
      <ErrorBoundary area="teste">
        <Broken />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Attempted to assign to readonly property.");
    expect(screen.getByRole("button", { name: "Recarregar a aplicação" })).toBeInTheDocument();
    await vi.waitFor(() => expect(calls.some((c) => c.path === "/api/diagnostics/client-error")).toBe(true));
    expect(calls.find((c) => c.path === "/api/diagnostics/client-error")?.body).toMatchObject({ source: "react:teste" });
    spy.mockRestore();
  });
});
