import { create } from "zustand";

/**
 * Sinais da interface que alimentam o núcleo UANJI (ver `useCoreState` em CoreOrb):
 * - flash: resultado da última operação (success / error), durante alguns segundos.
 * - executing: uma automação está a correr (pedido de execução activo).
 * - responding: o assistente está a gerar resposta.
 * Os estados de voz (a ouvir, a falar…) vêm do serviço de voz real, via SSE.
 */

interface CoreStore {
  flash: "success" | "error" | null;
  executing: number;
  responding: boolean;
  setFlash: (s: "success" | "error") => void;
  beginExecute: () => void;
  endExecute: () => void;
  setResponding: (v: boolean) => void;
}

let flashTimer: number | undefined;

export const useCore = create<CoreStore>((set, get) => ({
  flash: null,
  executing: 0,
  responding: false,
  setFlash: (s) => {
    window.clearTimeout(flashTimer);
    set({ flash: s });
    flashTimer = window.setTimeout(() => set({ flash: null }), 2200);
  },
  beginExecute: () => set({ executing: get().executing + 1 }),
  endExecute: () => set({ executing: Math.max(0, get().executing - 1) }),
  setResponding: (v) => set({ responding: v }),
}));
