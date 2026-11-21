import type { CardId, CardLayout, CardSize } from "@/api/types";

/** Disposição por omissão do painel inicial (ordem, tamanho). */
export const DEFAULT_CARDS: CardLayout[] = [
  { id: "tasks", size: "m", hidden: false },
  { id: "assistant", size: "m", hidden: false },
  { id: "alerts", size: "m", hidden: false },
  { id: "projects", size: "m", hidden: false },
  { id: "agenda", size: "m", hidden: false },
  { id: "performance", size: "m", hidden: false },
  { id: "knowledge", size: "s", hidden: false },
  { id: "automations", size: "s", hidden: false },
  { id: "integrations", size: "s", hidden: false },
  { id: "system", size: "s", hidden: false },
];

export const CARD_LABEL: Record<CardId, string> = {
  tasks: "Tarefas",
  projects: "Projectos",
  assistant: "Assistente UANJI",
  alerts: "Alertas e recomendações",
  agenda: "Agenda de hoje",
  performance: "Desempenho",
  knowledge: "Conhecimento",
  automations: "Automações",
  integrations: "Integrações",
  system: "Sistema",
};

/** Área da aplicação correspondente a cada card (para o modo adaptativo). */
const AREA: Record<CardId, string> = {
  tasks: "tasks",
  projects: "projects",
  assistant: "assistant",
  alerts: "home",
  agenda: "agenda",
  performance: "metrics",
  knowledge: "notes",
  automations: "automations",
  integrations: "integrations",
  system: "settings",
};

export const SIZE_CLASS: Record<CardSize, string> = {
  s: "xl:col-span-3",
  m: "xl:col-span-4",
  l: "lg:col-span-2 xl:col-span-6",
  xl: "lg:col-span-2 xl:col-span-12",
};
export const SIZE_LABEL: Record<CardSize, string> = { s: "Pequeno", m: "Médio", l: "Grande", xl: "Largura total" };

/** Completa a disposição guardada com cards novos/ausentes e remove ids desconhecidos. */
export function normalizeLayout(saved: CardLayout[] | undefined): CardLayout[] {
  const known = new Set(DEFAULT_CARDS.map((c) => c.id));
  const out = (saved ?? []).filter((c) => known.has(c.id)).map((c) => ({ ...c, size: c.size ?? "m", hidden: c.hidden ?? false }));
  const seen = new Set(out.map((c) => c.id));
  for (const c of DEFAULT_CARDS) if (!seen.has(c.id)) out.push({ ...c });
  return out;
}

/**
 * Modo adaptativo: ordena pelos hábitos de utilização (áreas mais visitadas primeiro).
 * Alertas pendentes e atrasos sobem sempre; o assistente fica entre os três primeiros.
 */
export function adaptiveOrder(layout: CardLayout[], usage: Record<string, number>, urgent: CardId[] = []): CardLayout[] {
  const score = (c: CardLayout) => (urgent.includes(c.id) ? 1e6 : 0) + (usage[AREA[c.id]] ?? 0);
  const sorted = [...layout].sort((a, b) => score(b) - score(a));
  const ai = sorted.findIndex((c) => c.id === "assistant");
  if (ai > 2) {
    const [a] = sorted.splice(ai, 1);
    sorted.splice(1, 0, a!);
  }
  return sorted;
}

export function moveCard(layout: CardLayout[], id: CardId, delta: -1 | 1): CardLayout[] {
  const i = layout.findIndex((c) => c.id === id);
  const j = i + delta;
  if (i < 0 || j < 0 || j >= layout.length) return layout;
  const out = [...layout];
  [out[i], out[j]] = [out[j]!, out[i]!];
  return out;
}

export function updateCard(layout: CardLayout[], id: CardId, patch: Partial<CardLayout>): CardLayout[] {
  return layout.map((c) => (c.id === id ? { ...c, ...patch } : c));
}
