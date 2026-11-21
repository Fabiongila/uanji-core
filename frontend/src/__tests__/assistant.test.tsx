import { act, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import type { AssistantTurn, VoiceStatus } from "@/api/types";
import { CoreOrb, CORE_LABELS, type CoreState } from "@/components/CoreOrb";
import { VoiceSettingsPanel } from "@/features/VoiceSettings";
import AssistantPage from "@/pages/Assistant";
import DashboardPage from "@/pages/Dashboard";
import { useVoice } from "@/lib/voice";
import { emptyDashboard, mockApi, renderApp } from "@/test/utils";

export const voiceStatus = (over: Partial<VoiceStatus> = {}): VoiceStatus => ({
  state: "off",
  label: "Escuta desligada",
  listening_enabled: false,
  wake_word: "UAJI",
  conversation_id: null,
  mic: { permission: "authorized", active: false, temporary: false, device: null },
  wake: { mode: "system", samples: [], threshold: 0.16, last_score: null, preparing: false },
  stt: { engine: "vosk", local: true, model_installed: true, model: "vosk-model-small-pt-0.3", model_size_mb: 31 },
  tts: { available: true, enabled: true, speaking: false, can_resume: false, voice: "Joana", voice_found: true, last_error: "" },
  external_audio: false,
  audio_stored: false,
  last_error: "",
  partial: "",
  last_transcript: "",
  ...over,
});

const turn = (over: Partial<AssistantTurn> = {}): AssistantTurn => ({
  id: "t1",
  conversation_id: "c1",
  reply: "",
  speech: "",
  engine: "local",
  report: null,
  actions: [],
  executed: [],
  consulted: [],
  navigate: null,
  awaiting: null,
  control: null,
  error: false,
  ...over,
});

beforeEach(() => {
  useVoice.setState({ status: voiceStatus(), entries: [], partial: "", conversationId: null, connected: true });
});

describe("Núcleo holográfico", () => {
  it("mostra um indicador textual para cada estado do assistente", () => {
    const states: CoreState[] = ["idle", "wake", "listening", "interpreting", "preparing", "speaking", "executing", "confirming", "success", "error"];
    for (const s of states) {
      const { unmount } = renderApp(<CoreOrb state={s} />);
      expect(screen.getByRole("img", { name: `Núcleo UANJI: ${CORE_LABELS[s]}` })).toBeInTheDocument();
      expect(screen.getByText(CORE_LABELS[s])).toBeInTheDocument();
      unmount();
    }
  });
});

describe("Assistente", () => {
  it("envia texto, mostra relatório estruturado e pede voz quando escolhido", async () => {
    const { calls } = mockApi({
      "GET /health": { status: "ok", version: "0.1.0" },
      "GET /api/assistant/status": { configured: false, provider: "none", model: "", message: "" },
      "POST /api/assistant/message": turn({
        reply: "Relatório do dia.",
        report: {
          kind: "daily",
          title: "Relatório do dia",
          speech: "Relatório do dia.",
          sections: [
            { kind: "facts", title: "Factos registados", items: ["Concluiu 2 tarefas hoje"] },
            { kind: "unavailable", title: "Informação indisponível", items: ["Trabalho fora da aplicação não é conhecido"] },
          ],
        },
      }),
    });
    renderApp(<AssistantPage />);
    await userEvent.type(screen.getByLabelText("Mensagem para o assistente"), "faz o relatório do meu dia{Enter}");
    expect(await screen.findByText("Concluiu 2 tarefas hoje")).toBeInTheDocument();
    expect(screen.getByText("Factos registados")).toBeInTheDocument();
    expect(screen.getByText("Informação indisponível")).toBeInTheDocument();
    const sent = calls.find((c) => c.path === "/api/assistant/message");
    expect(sent?.body).toMatchObject({ text: "faz o relatório do meu dia", speak: true });
  });

  it("acções destrutivas mostram o que muda e só executam após confirmação", async () => {
    const pending = {
      id: "a1", tool: "delete_task", summary: "Eliminar a tarefa «X»", risk: "destructive" as const,
      details: ["Esta operação não pode ser desfeita (só por restauro de backup)."], status: "pending" as const, message: "",
    };
    const { calls } = mockApi({
      "GET /health": { status: "ok", version: "0.1.0" },
      "GET /api/assistant/status": { configured: false, provider: "none", model: "", message: "" },
      "POST /api/assistant/message": turn({ reply: "Preciso da sua confirmação.", actions: [pending], awaiting: "confirmation" }),
      "POST /api/assistant/actions/a1": turn({ id: "t2", reply: "Tarefa eliminada: «X».", actions: [{ ...pending, status: "confirmed" }], executed: [{ tool: "delete_task", message: "ok", entity: null }] }),
    });
    renderApp(<AssistantPage />);
    await userEvent.type(screen.getByLabelText("Mensagem para o assistente"), "apaga a tarefa X{Enter}");
    expect(await screen.findByText(/não pode ser desfeita/)).toBeInTheDocument();
    expect(screen.getByText("irreversível")).toBeInTheDocument();
    expect(calls.some((c) => c.path === "/api/assistant/actions/a1")).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "Confirmar" }));
    expect(await screen.findByText("Tarefa eliminada: «X».")).toBeInTheDocument();
    expect(calls.find((c) => c.path === "/api/assistant/actions/a1")?.body).toEqual({ approve: true });
  });

  it("indica privacidade, permissão negada e mostra a transcrição parcial", async () => {
    mockApi({ "GET /health": { status: "ok" }, "GET /api/assistant/status": { configured: false } });
    useVoice.setState({ status: voiceStatus({ mic: { permission: "denied", active: false, temporary: false, device: null }, last_error: "O acesso ao microfone foi negado." }) });
    renderApp(<AssistantPage />);
    expect(await screen.findByText("Microfone negado")).toBeInTheDocument();
    expect(screen.getByText("Microfone fechado")).toBeInTheDocument();
    expect(screen.getByText(/Áudio processado localmente/)).toBeInTheDocument();
    expect(screen.getByText(/O acesso ao microfone foi negado/)).toBeInTheDocument();
    act(() => useVoice.setState({ partial: "quais são as" }));
    expect(screen.getByText("quais são as…")).toBeInTheDocument();
  });

  it("botão do microfone explica a utilização antes da primeira vez e depois activa", async () => {
    localStorage.removeItem("uanji.mic.explained");
    const { calls } = mockApi({ "GET /health": { status: "ok" }, "GET /api/assistant/status": { configured: false }, "POST /api/voice/activate": voiceStatus({ state: "listening" }) });
    renderApp(<AssistantPage />);
    await userEvent.click(screen.getAllByRole("button", { name: "Falar com o assistente" })[0]!);
    expect(await screen.findByText(/Processamento local:/)).toBeInTheDocument();
    expect(calls.some((c) => c.path === "/api/voice/activate")).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "Compreendo, continuar" }));
    await screen.findByText("Microfone autorizado");
    expect(calls.some((c) => c.path === "/api/voice/activate")).toBe(true);
  });
});

describe("Dashboard holográfico", () => {
  it("apresenta os cards principais com dados reais e o núcleo segue o estado de voz", async () => {
    mockApi({
      "GET /health": { status: "ok" },
      "GET /api/dashboard": { ...emptyDashboard, is_empty: false, counters: { ...emptyDashboard.counters, pending_tasks: 3, active_projects: 2 } },
      "GET /api/agenda": { events: [], tasks: [], start: "", end: "" },
      "GET /api/notes": { items: [], total: 0, limit: 50, offset: 0 },
      "GET /api/automations": [],
      "GET /api/integrations": [],
      "GET /api/diagnostics": { db_size_bytes: 1000, disk_free_bytes: 10, vault: { secure: true }, schema_revision: "0003", schema_head: "0003" },
    });
    useVoice.setState({ status: voiceStatus({ state: "speaking" }) });
    renderApp(<DashboardPage />);
    for (const name of ["Tarefas", "Projectos", "Assistente UANJI", "Alertas e recomendações", "Agenda de hoje", "Desempenho", "Conhecimento", "Automações", "Integrações", "Sistema"]) {
      expect(await screen.findByRole("region", { name })).toBeInTheDocument();
    }
    const assistant = screen.getByRole("region", { name: "Assistente UANJI" });
    expect(within(assistant).getByText("A falar")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Tarefas" })).getByText("3")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Abrir Projectos" })).toHaveAttribute("href", "/projects");
  });
});

describe("Voz e personalidade", () => {
  const settings = {
    theme: "uanji-dark", reduced_motion: false, timezone: "Africa/Luanda",
    notifications: { enabled: true, native: false, categories: {}, deadline_hours: 24, quiet_start: "22:00", quiet_end: "07:00", daily_review_time: "18:00", weekly_review_day: 4 },
    backups: { automatic: true, interval_hours: 24, keep: 10 },
    assistant: { provider: "none", model: "", base_url: "", secret_id: null, confirm_creates: false, confirm_updates: true, history_days: 30, context_turns: 12 },
    voice: { listening: false, wake_word: "UAJI", sensitivity: 1, greeting: "Estou aqui. Em que posso ajudar?", tts_enabled: true, voice: "Joana", rate: 185, volume: 0.9, language: "pt-PT", follow_up_seconds: 8 },
    persona: { address: "neutral" as const, custom: "" },
    activity: { enabled: false, sample_seconds: 15, idle_seconds: 300, capture_titles: false, excluded_apps: [], retention_days: 30, git_folders: [] },
    proactive: { enabled: true, voice: true, intensity: "normal" as const, rules: {} },
    system: { allow_apps: true, confirm_system: false, allow_shell: false },
    appearance: { theme: "uanji-dark" as const, accent: "cyan" as const, density: "comfortable" as const, font_scale: 100, sidebar: "left" as const, layout_mode: "custom" as const, cards: [] },
    usage: {},
  };
  const voices = {
    available: true,
    notes: ["O macOS não inclui vozes de português de Angola."],
    voices: [
      { id: "Joana", name: "Joana", language: "pt-PT", gender: "female", gender_source: "system", quality: "default" },
      { id: "Eddy (Português (Brasil))", name: "Eddy", language: "pt-BR", gender: "male", gender_source: "catalog", quality: "default" },
    ],
  };

  it("lista só vozes instaladas, filtra por tipo e guarda tratamento sem tocar na escuta", async () => {
    const { calls } = mockApi({ "GET /api/voice/voices": voices, "PATCH /api/settings": settings, "POST /api/voice/test": { ok: true } });
    renderApp(<VoiceSettingsPanel settings={settings} />);
    await screen.findByRole("option", { name: /Eddy/ });
    expect(within(screen.getByLabelText("Voz")).getAllByRole("option")).toHaveLength(2);
    await userEvent.selectOptions(screen.getByLabelText("Tipo de voz"), "male");
    expect(within(screen.getByLabelText("Voz")).getByRole("option", { name: /Eddy — pt-BR \(masculina\)/ })).toBeInTheDocument();
    expect(screen.getByText(/português de Angola/)).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Voz"), "Eddy (Português (Brasil))");
    await userEvent.click(screen.getByRole("button", { name: "Ouvir amostra" }));
    expect(calls.find((c) => c.path === "/api/voice/test")?.body).toMatchObject({ voice: "Eddy (Português (Brasil))" });

    await userEvent.click(screen.getByRole("radio", { name: /Personalizado/ }));
    await userEvent.type(screen.getByLabelText("Nome ou forma de tratamento"), "Chefe");
    await userEvent.click(screen.getByRole("button", { name: "Guardar voz e personalidade" }));
    const body = calls.find((c) => c.method === "PATCH")?.body as { values: Record<string, Record<string, unknown>> };
    expect(body.values.persona).toEqual({ address: "custom", custom: "Chefe" });
    expect(body.values.voice?.voice).toBe("Eddy (Português (Brasil))");
    expect(body.values.voice).not.toHaveProperty("listening");
  });

  it("explica quando não há voz do tipo pedido", async () => {
    mockApi({ "GET /api/voice/voices": { ...voices, voices: [voices.voices[0]] } });
    renderApp(<VoiceSettingsPanel settings={settings} />);
    await screen.findByRole("option", { name: /Joana — pt-PT/ });
    await userEvent.selectOptions(screen.getByLabelText("Tipo de voz"), "male");
    expect(screen.getByText("Não há nenhuma voz masculina instalada.")).toBeInTheDocument();
  });
});
