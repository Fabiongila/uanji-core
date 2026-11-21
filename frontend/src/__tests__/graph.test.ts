import { describe, expect, it } from "vitest";
import { chainFromGraph, graphFromDefinition, nextStepId, TRIGGER_ID, type FlowNode } from "@/features/automation/graph";

const step = (id: string): FlowNode => ({ id, position: { x: 0, y: 0 }, data: { kind: "step", step: { id, action: "log_event", params: { message: id } } } });
const trigger: FlowNode = { id: TRIGGER_ID, position: { x: 0, y: 0 }, data: { kind: "trigger" } };

describe("construtor de automações: ordem a partir do grafo", () => {
  it("segue as arestas a partir do gatilho, independentemente da ordem dos nós", () => {
    const nodes = [step("b"), trigger, step("a")];
    const edges = [{ id: "1", source: TRIGGER_ID, target: "a" }, { id: "2", source: "a", target: "b" }];
    const r = chainFromGraph(nodes, edges);
    expect(r.errors).toEqual([]);
    expect(r.steps.map((s) => s.id)).toEqual(["a", "b"]);
  });

  it("recusa ramificações, nós soltos e ciclos", () => {
    const nodes = [trigger, step("a"), step("b"), step("c")];
    const branch = chainFromGraph(nodes, [
      { id: "1", source: TRIGGER_ID, target: "a" },
      { id: "2", source: TRIGGER_ID, target: "b" },
    ]);
    expect(branch.errors.join(" ")).toMatch(/mais de uma saída/);
    expect(branch.errors.join(" ")).toMatch(/não ligad/);
    const cycle = chainFromGraph([trigger, step("a"), step("b")], [
      { id: "1", source: TRIGGER_ID, target: "a" },
      { id: "2", source: "a", target: "b" },
      { id: "3", source: "b", target: "a" },
    ]);
    expect(cycle.errors.join(" ")).toMatch(/ciclo|mais de uma entrada/);
  });

  it("exige pelo menos uma acção", () => {
    expect(chainFromGraph([trigger], []).errors[0]).toMatch(/pelo menos uma acção/);
  });

  it("um nó Condição aplica-se à acção seguinte e é reconstruído a partir da definição", () => {
    const cond: FlowNode = { id: "c1", position: { x: 0, y: 0 }, data: { kind: "condition", conditions: [{ field: "trigger.title", op: "contains", value: "bug" }], on_false: "stop" } };
    const r = chainFromGraph([trigger, cond, step("a"), step("b")], [
      { id: "1", source: TRIGGER_ID, target: "c1" },
      { id: "2", source: "c1", target: "a" },
      { id: "3", source: "a", target: "b" },
    ]);
    expect(r.errors).toEqual([]);
    expect(r.steps[0]).toMatchObject({ id: "a", on_false: "stop", conditions: [{ field: "trigger.title" }] });
    expect(r.steps[1]!.conditions).toBeUndefined();
    const g = graphFromDefinition({ trigger: { type: "manual", config: {} }, conditions: [], steps: r.steps });
    expect(g.nodes.map((n) => n.data.kind)).toEqual(["trigger", "condition", "step", "step"]);
    expect(chainFromGraph([trigger, cond], [{ id: "1", source: TRIGGER_ID, target: "c1" }]).errors.join(" ")).toMatch(/seguida por uma acção/);
  });

  it("reconstrói o grafo a partir da definição e gera ids livres", () => {
    const g = graphFromDefinition({ trigger: { type: "manual", config: {} }, conditions: [], steps: [{ id: "s1", action: "notify", params: {} }] });
    expect(g.edges).toEqual([{ id: "e-trigger-s1", source: TRIGGER_ID, target: "s1" }]);
    expect(nextStepId(g.nodes)).toBe("s2");
  });
});
