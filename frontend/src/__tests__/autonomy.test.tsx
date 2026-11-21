import { act, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import type { AssistantTurn } from "@/api/types";
import { adaptiveOrder, DEFAULT_CARDS, moveCard, normalizeLayout } from "@/features/dashboard-layout";
import { TurnView } from "@/features/assistant";
import { useApplyAppearance, DEFAULT_APPEARANCE } from "@/lib/appearance";
import { useVoice } from "@/lib/voice";
import DashboardPage from "@/pages/Dashboard";
import { emptyDashboard, mockApi, renderApp } from "@/test/utils";
import { voiceStatus } from "./assistant.test";

beforeEach(() => {
  useVoice.setState({ status: voiceStatus(), entries: [], partial: "", conversationId: null, connected: true });
});

describe("Disposição do painel", () => {
  it("completa disposições antigas, move cards e ordena pelo uso (alertas primeiro)", () => {
    const l = normalizeLayout([{ id: "agenda", size: "l", hidden: false }]);
    expect(l[0]).toEqual({ id: "agenda", size: "l", hidden: false });
    expect(l).toHaveLength(DEFAULT_CARDS.length);
    expect(moveCard(l, "agenda", 1)[1]!.id).toBe("agenda");
    const adapted = adaptiveOrder(DEFAULT_CARDS, { notes: 30, metrics: 12, tasks: 1 }, ["alerts"]);
    expect(adapted.map((c) => c.id).slice(0, 4)).toEqual(["alerts", "assistant", "knowledge", "performance"]);
  });

  it("permite esconder um card e guarda a nova disposição", async () => {
    const settings = { appearance: { ...DEFAULT_APPEARANCE }, usage: {} };
    const { calls } = mockApi({
      "GET /health": { status: "ok" },
      "GET /api/settings": settings,
      "PATCH /api/settings": settings,
      "GET /api/dashboard": { ...emptyDashboard, is_empty: false },
      "GET /api/agenda": { events: [], tasks: [] },
      "GET /api/notes": { items: [], total: 0 },
      "GET /api/automations": [],
      "GET /api/integrations": [],
      "GET /api/diagnostics": { db_size_bytes: 1, disk_free_bytes: 1, vault: { secure: true }, schema_revision: "0004", schema_head: "0004" },
    });
    renderApp(<DashboardPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Personalizar painel" }));
    await userEvent.click(screen.getByRole("button", { name: "Esconder Agenda de hoje" }));
    expect(screen.queryByRole("region", { name: "Agenda de hoje" })).not.toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Tamanho de Tarefas"), "l");
    await userEvent.click(screen.getByRole("button", { name: "Guardar disposição" }));
    const body = calls.find((c) => c.method === "PATCH")?.body as { values: { appearance: { cards: { id: string; size: string; hidden: boolean }[] } } };
    const cards = body.values.appearance.cards;
    expect(cards.find((c) => c.id === "agenda")?.hidden).toBe(true);
    expect(cards.find((c) => c.id === "tasks")?.size).toBe("l");
  });
});

describe("Aparência", () => {
  function Probe({ theme }: { theme: "light" | "contrast" }) {
    useApplyAppearance({ ...DEFAULT_APPEARANCE, theme, accent: "violet", font_scale: 110 });
    return null;
  }
  it("aplica tema, cor de destaque e escala ao documento", () => {
    renderApp(<Probe theme="light" />);
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(document.documentElement.dataset.accent).toBe("violet");
    expect(document.documentElement.style.getPropertyValue("--ui-zoom")).toBe("1.1");
  });
});

describe("Iniciativa do assistente", () => {
  it("mostra a mensagem como iniciativa e responde «sim» com um clique", async () => {
    const turn: AssistantTurn = {
      id: "p1", conversation_id: "c9", reply: "Bom dia. Quer que leia as prioridades?", speech: "", engine: "local", report: null,
      actions: [], executed: [], consulted: [], navigate: null, awaiting: "offer", control: null, error: false,
      proactive: "morning", offer: { tool: "build_report", label: "Ler as prioridades" },
    };
    const { calls } = mockApi({ "POST /api/assistant/message": { ...turn, id: "r1", reply: "Próximos passos.", proactive: undefined, offer: null, awaiting: null } });
    act(() => useVoice.getState().addTurn(turn, "proactive"));
    renderApp(<TurnView entry={useVoice.getState().entries[0]!} />);
    expect(screen.getByText("Por iniciativa do assistente")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Sim — Ler as prioridades" }));
    expect(calls.find((c) => c.path === "/api/assistant/message")?.body).toMatchObject({ text: "sim", conversation_id: "c9" });
    expect(await screen.findByText("Respondeu «sim».")).toBeInTheDocument();
    expect(within(document.body).queryByRole("button", { name: "Agora não" })).not.toBeInTheDocument();
  });
});
