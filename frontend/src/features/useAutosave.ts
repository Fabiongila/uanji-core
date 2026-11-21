import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "@/api/client";

export type SaveState = "saved" | "dirty" | "saving" | "error" | "conflict";

const DRAFT_PREFIX = "uanji.draft.";

export interface Draft<T> {
  baseRevision: number;
  value: T;
  savedAt: number;
}

export function readDraft<T>(key: string): Draft<T> | null {
  try {
    const raw = localStorage.getItem(DRAFT_PREFIX + key);
    return raw ? (JSON.parse(raw) as Draft<T>) : null;
  } catch {
    return null;
  }
}

export function clearDraft(key: string): void {
  try {
    localStorage.removeItem(DRAFT_PREFIX + key);
  } catch {
    /* indisponível */
  }
}

function writeDraft<T>(key: string, d: Draft<T>): void {
  try {
    localStorage.setItem(DRAFT_PREFIX + key, JSON.stringify(d));
  } catch {
    /* indisponível */
  }
}

/**
 * Gravação automática com debounce.
 * - Cada alteração é escrita imediatamente num rascunho local (sobrevive a fechar a app).
 * - O envio ao backend inclui a revisão conhecida; um 409 indica conflito (nada é sobrescrito).
 * - Ao desmontar (mudar de página), as alterações pendentes são enviadas.
 */
export function useAutosave<T>({
  key,
  revision,
  save,
  delay = 900,
}: {
  key: string;
  revision: number;
  save: (value: T, baseRevision: number) => Promise<{ revision: number }>;
  delay?: number;
}) {
  const [state, setState] = useState<SaveState>("saved");
  const [lastError, setLastError] = useState<string | null>(null);
  const pending = useRef<T | null>(null);
  const rev = useRef(revision);
  const timer = useRef<number | undefined>(undefined);
  const inflight = useRef<Promise<void> | null>(null);
  const saveRef = useRef(save);
  saveRef.current = save;

  useEffect(() => {
    rev.current = revision;
  }, [revision]);

  const flush = useCallback(async (): Promise<void> => {
    window.clearTimeout(timer.current);
    if (inflight.current) await inflight.current;
    const value = pending.current;
    if (value === null) return;
    pending.current = null;
    setState("saving");
    const p = (async () => {
      try {
        const res = await saveRef.current(value, rev.current);
        rev.current = res.revision;
        if (pending.current === null) {
          clearDraft(key);
          setState("saved");
        } else setState("dirty");
        setLastError(null);
      } catch (e) {
        pending.current ??= value;
        if (e instanceof ApiError && e.status === 409) setState("conflict");
        else setState("error");
        setLastError(e instanceof Error ? e.message : "Erro ao gravar.");
      }
    })();
    inflight.current = p;
    await p;
    inflight.current = null;
  }, [key]);

  const change = useCallback(
    (value: T) => {
      pending.current = value;
      writeDraft(key, { baseRevision: rev.current, value, savedAt: Date.now() });
      setState("dirty");
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => void flush(), delay);
    },
    [key, delay, flush],
  );

  useEffect(() => {
    const onUnload = (e: BeforeUnloadEvent) => {
      if (pending.current !== null) {
        void flush();
        e.preventDefault();
      }
    };
    window.addEventListener("beforeunload", onUnload);
    return () => {
      window.removeEventListener("beforeunload", onUnload);
      void flush();
    };
  }, [flush]);

  return { state, lastError, change, flush, setRevision: (r: number) => (rev.current = r) };
}

export const SAVE_LABEL: Record<SaveState, string> = {
  saved: "Guardado",
  dirty: "Alterações por guardar…",
  saving: "A guardar…",
  error: "Falha ao guardar — rascunho mantido localmente",
  conflict: "Conflito: a nota foi alterada noutro local",
};
