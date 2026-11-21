import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { create } from "zustand";
import { api, getBackendConfig } from "@/api/client";
import type { AssistantTurn, VoiceStatus } from "@/api/types";

/**
 * Estado do assistente partilhado por toda a interface: estado real do serviço de voz
 * (recebido por SSE) e a conversa da sessão actual.
 */
export interface Entry {
  id: string;
  role: "user" | "assistant";
  text: string;
  source: "voice" | "text" | "proactive";
  turn?: AssistantTurn;
  at: number;
}

interface VoiceStore {
  status: VoiceStatus | null;
  connected: boolean;
  partial: string;
  conversationId: string | null;
  entries: Entry[];
  setStatus: (s: VoiceStatus) => void;
  setConnected: (c: boolean) => void;
  setPartial: (p: string) => void;
  addUser: (text: string, source: Entry["source"]) => void;
  addTurn: (turn: AssistantTurn, source: Entry["source"]) => void;
  updateAction: (turn: AssistantTurn) => void;
  clear: () => void;
}

const MAX_ENTRIES = 200;
let seq = 0;

export const useVoice = create<VoiceStore>((set) => ({
  status: null,
  connected: false,
  partial: "",
  conversationId: null,
  entries: [],
  setStatus: (status) => set({ status }),
  setConnected: (connected) => set({ connected }),
  setPartial: (partial) => set({ partial }),
  addUser: (text, source) =>
    set((s) => ({ entries: [...s.entries, { id: `u${++seq}`, role: "user" as const, text, source, at: Date.now() }].slice(-MAX_ENTRIES), partial: "" })),
  addTurn: (turn, source) =>
    set((s) => ({
      conversationId: turn.conversation_id,
      entries: [...s.entries, { id: turn.id, role: "assistant" as const, text: turn.reply, source, turn, at: Date.now() }].slice(-MAX_ENTRIES),
    })),
  // Uma decisão (confirmar/rejeitar) actualiza a acção na mensagem original e acrescenta o resultado.
  updateAction: (result) =>
    set((s) => {
      const decided = new Map(result.actions.map((a) => [a.id, a]));
      const entries = s.entries.map((e) =>
        e.turn && e.turn.actions.some((a) => decided.has(a.id))
          ? { ...e, turn: { ...e.turn, actions: e.turn.actions.map((a) => decided.get(a.id) ?? a), awaiting: null } }
          : e,
      );
      return { entries: [...entries, { id: result.id, role: "assistant" as const, text: result.reply, source: "text" as const, turn: result, at: Date.now() }] };
    }),
  clear: () => set({ entries: [], conversationId: null }),
}));

// --------------------------------------------------------------------------- Comandos

export const voiceApi = {
  activate: () => api.post<VoiceStatus>("/api/voice/activate"),
  cancel: () => api.post<VoiceStatus>("/api/voice/cancel"),
  stopSpeaking: () => api.post<VoiceStatus>("/api/voice/stop-speaking"),
  resumeSpeaking: () => api.post<VoiceStatus>("/api/voice/resume-speaking"),
  setListening: (enabled: boolean) => api.put<VoiceStatus>("/api/voice/listening", { enabled }),
  speak: (text: string) => api.post<VoiceStatus>("/api/voice/speak", { text }),
};

export async function sendMessage(text: string, speak: boolean): Promise<AssistantTurn> {
  const store = useVoice.getState();
  store.addUser(text, "text");
  const turn = await api.post<AssistantTurn>("/api/assistant/message", { text, conversation_id: store.conversationId, speak });
  useVoice.getState().addTurn(turn, "text");
  return turn;
}

export async function decideAction(id: string, approve: boolean): Promise<AssistantTurn> {
  const turn = await api.post<AssistantTurn>(`/api/assistant/actions/${id}`, { approve });
  useVoice.getState().updateAction(turn);
  return turn;
}

// --------------------------------------------------------------------------- Eventos (SSE)

type VoiceEvent =
  | { type: "status"; status: VoiceStatus }
  | { type: "partial"; text: string }
  | { type: "transcript"; text: string }
  | { type: "turn"; turn: AssistantTurn; source: "voice" | "text"; text: string }
  | { type: "proactive"; turn: AssistantTurn }
  | { type: "wake" }
  | { type: "wake_score"; score: number | null; threshold: number; hit: boolean };

/** Lê o fluxo SSE com `fetch` (o EventSource não permite o cabeçalho Authorization). */
async function readStream(signal: AbortSignal, onEvent: (e: VoiceEvent) => void): Promise<void> {
  const cfg = await getBackendConfig();
  const res = await fetch(`${cfg.baseUrl}/api/voice/events`, {
    headers: cfg.token ? { Authorization: `Bearer ${cfg.token}` } : {},
    signal,
  });
  if (!res.ok || !res.body) throw new Error(`SSE ${res.status}`);
  useVoice.getState().setConnected(true);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      const data = chunk
        .split("\n")
        .filter((l) => l.startsWith("data: "))
        .map((l) => l.slice(6))
        .join("\n");
      if (data) {
        try {
          onEvent(JSON.parse(data) as VoiceEvent);
        } catch {
          /* evento malformado: ignorado */
        }
      }
    }
  }
}

/** Montado uma vez (AppShell): mantém o estado de voz sincronizado e aplica navegação pedida por voz. */
let onProactive: ((t: AssistantTurn) => void) | undefined;
/** Permite à interface reagir a mensagens por iniciativa (ex.: mostrar um aviso). */
export function setProactiveListener(fn: ((t: AssistantTurn) => void) | undefined) {
  onProactive = fn;
}

export function useVoiceEvents() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  useEffect(() => {
    if (typeof fetch !== "function" || typeof TextDecoder === "undefined") return;
    const ctrl = new AbortController();
    let retry: number | undefined;
    const store = useVoice.getState;
    const onEvent = (e: VoiceEvent) => {
      if (e.type === "status") store().setStatus(e.status);
      else if (e.type === "partial") store().setPartial(e.text);
      else if (e.type === "transcript") store().addUser(e.text, "voice");
      else if (e.type === "turn" && e.source === "voice") {
        store().addTurn(e.turn, "voice");
        if (e.turn.executed.length || e.turn.actions.some((a) => a.status === "confirmed")) void qc.invalidateQueries();
        if (e.turn.navigate) navigate(e.turn.navigate);
      } else if (e.type === "proactive") {
        // O assistente tomou a iniciativa: entra na conversa e aparece como aviso.
        store().addTurn(e.turn, "proactive");
        void qc.invalidateQueries({ queryKey: ["notifications"] });
        onProactive?.(e.turn);
      }
    };
    const connect = async () => {
      try {
        await readStream(ctrl.signal, onEvent);
      } catch {
        /* backend indisponível ou a reiniciar */
      }
      store().setConnected(false);
      if (!ctrl.signal.aborted) retry = window.setTimeout(() => void connect(), 4000);
    };
    void connect();
    return () => {
      ctrl.abort();
      window.clearTimeout(retry);
    };
  }, [navigate, qc]);
}

/** Esc interrompe a fala do assistente (quando nenhum diálogo está aberto). */
export function useStopSpeechShortcut() {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || document.querySelector("dialog[open]")) return;
      const s = useVoice.getState().status;
      if (s?.tts.speaking || s?.state === "listening") {
        void (s.tts.speaking ? voiceApi.stopSpeaking() : voiceApi.cancel()).catch(() => undefined);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}
