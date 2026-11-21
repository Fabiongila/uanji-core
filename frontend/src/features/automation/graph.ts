import type { AutomationCondition, AutomationDefinition, AutomationStep } from "@/api/types";

export const TRIGGER_ID = "trigger";

export type ConditionData = { kind: "condition"; conditions: AutomationCondition[]; on_false: "skip" | "stop" };

export interface FlowNode {
  id: string;
  position: { x: number; y: number };
  data: { kind: "trigger" } | { kind: "step"; step: AutomationStep } | ConditionData;
}
export interface FlowEdge {
  id: string;
  source: string;
  target: string;
}

const condId = (stepId: string) => `c-${stepId}`;

/**
 * Constrói nós/arestas a partir da definição (posições em `ui.positions`).
 * As condições de uma etapa aparecem como um nó «Condição» imediatamente antes dela.
 */
export function graphFromDefinition(def: AutomationDefinition): { nodes: FlowNode[]; edges: FlowEdge[] } {
  const pos = ((def.ui?.positions ?? {}) as Record<string, { x: number; y: number }>) || {};
  const nodes: FlowNode[] = [{ id: TRIGGER_ID, position: pos[TRIGGER_ID] ?? { x: 0, y: 0 }, data: { kind: "trigger" } }];
  const ids = [TRIGGER_ID];
  let y = 0;
  for (const s of def.steps) {
    if (s.conditions && s.conditions.length) {
      y += 120;
      const cid = condId(s.id);
      nodes.push({ id: cid, position: pos[cid] ?? { x: 0, y }, data: { kind: "condition", conditions: s.conditions, on_false: s.on_false ?? "skip" } });
      ids.push(cid);
    }
    y += 120;
    const { conditions: _c, on_false: _o, ...plain } = s;
    void _c;
    void _o;
    nodes.push({ id: s.id, position: pos[s.id] ?? { x: 0, y }, data: { kind: "step", step: plain } });
    ids.push(s.id);
  }
  const edges = ids.slice(1).map((id, i) => ({ id: `e-${ids[i]}-${id}`, source: ids[i]!, target: id }));
  return { nodes, edges };
}

/**
 * Deriva a ordem das etapas a partir do grafo: Gatilho → [Condição] → Acção → … → Resultado.
 * Cada nó tem no máximo uma saída e uma entrada; sem ciclos; tudo ligado.
 * Um nó «Condição» aplica-se à acção seguinte.
 */
export function chainFromGraph(nodes: FlowNode[], edges: FlowEdge[]): { steps: AutomationStep[]; errors: string[] } {
  const errors: string[] = [];
  const out = new Map<string, string[]>();
  const inc = new Map<string, number>();
  for (const e of edges) {
    out.set(e.source, [...(out.get(e.source) ?? []), e.target]);
    inc.set(e.target, (inc.get(e.target) ?? 0) + 1);
  }
  for (const [id, targets] of out) if (targets.length > 1) errors.push(`O nó «${id}» tem mais de uma saída (a execução é sequencial).`);
  for (const [id, n] of inc) if (n > 1) errors.push(`O nó «${id}» tem mais de uma entrada.`);
  if ((inc.get(TRIGGER_ID) ?? 0) > 0) errors.push("O gatilho não pode ter entradas.");
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const steps: AutomationStep[] = [];
  const seen = new Set<string>([TRIGGER_ID]);
  let pending: ConditionData | null = null;
  let cur = out.get(TRIGGER_ID)?.[0];
  while (cur) {
    if (seen.has(cur)) {
      errors.push("O fluxo contém um ciclo.");
      break;
    }
    seen.add(cur);
    const node = byId.get(cur);
    if (node?.data.kind === "condition") {
      if (pending) errors.push("Duas condições seguidas: junte-as num só nó.");
      if (!node.data.conditions.length) errors.push(`O nó de condição «${node.id}» não tem regras.`);
      pending = node.data;
    } else if (node?.data.kind === "step") {
      steps.push(pending ? { ...node.data.step, conditions: pending.conditions, on_false: pending.on_false } : node.data.step);
      pending = null;
    }
    cur = out.get(cur)?.[0];
  }
  if (pending) errors.push("Uma condição tem de ser seguida por uma acção ou resultado.");
  const orphans = nodes.filter((n) => n.data.kind !== "trigger" && !seen.has(n.id));
  if (orphans.length) errors.push(`Nós não ligados ao fluxo: ${orphans.map((o) => o.id).join(", ")}.`);
  if (steps.length === 0) errors.push("Adicione e ligue pelo menos uma acção ao gatilho.");
  return { steps, errors };
}

export function nextStepId(nodes: FlowNode[], prefix = "s"): string {
  let i = 1;
  const ids = new Set(nodes.map((n) => n.id));
  while (ids.has(`${prefix}${i}`)) i++;
  return `${prefix}${i}`;
}
