import {
  addEdge,
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Ban, CheckCircle2, Copy, GitBranch, KeyRound, Play, Plus, Save, Trash2, Zap } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, ApiError, errorMessage } from "@/api/client";
import { useActionCatalog, useApiMutation, useAutomation, useAutomationRuns, useProjects, useRun } from "@/api/hooks";
import type { ActionSpec, Automation, AutomationCondition, AutomationDefinition, AutomationStep } from "@/api/types";
import { Badge, Button, Checkbox, ConfirmDialog, Dialog, ErrorState, Field, Input, Loading, Panel, Select, Tabs, Textarea } from "@/components/ui";
import { chainFromGraph, graphFromDefinition, nextStepId, TRIGGER_ID, type ConditionData, type FlowEdge, type FlowNode } from "@/features/automation/graph";
import { toast } from "@/lib/toast";
import { cn, fmtDateTime } from "@/lib/utils";
import { RUN_LABEL, RUN_TONE, TRIGGER_LABEL, useRunAutomation } from "./Automations";

type NodeData = FlowNode["data"] & { label?: string; error?: boolean; result?: boolean };

const EMPTY: AutomationDefinition = { trigger: { type: "manual", config: {} }, conditions: [], steps: [] };

function TriggerNode({ data, selected }: NodeProps<Node<NodeData>>) {
  return (
    <div className={cn("w-56 rounded-lg border bg-surface-2 px-3 py-2 text-xs", selected ? "border-amber" : "border-amber/50")}>
      <div className="flex items-center gap-1.5 text-amber"><Zap className="h-3.5 w-3.5" /> GATILHO</div>
      <div className="mt-0.5 text-[13px] text-text">{data.label}</div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

function StepNode({ data, selected }: NodeProps<Node<NodeData>>) {
  const step = data.kind === "step" ? data.step : null;
  return (
    <div className={cn("w-56 rounded-lg border bg-surface-2 px-3 py-2 text-xs", data.error ? "border-danger" : selected ? (data.result ? "border-success" : "border-primary") : data.result ? "border-success/50" : "border-line-strong")}>
      <Handle type="target" position={Position.Top} />
      <div className={cn("flex items-center justify-between", data.result ? "text-success" : "text-primary")}>
        <span className="flex items-center gap-1">{data.result && <CheckCircle2 className="h-3.5 w-3.5" />}{data.result ? "RESULTADO" : "ACÇÃO"}</span>
        <span className="font-mono text-muted">{step?.id}</span>
      </div>
      <div className="mt-0.5 text-[13px] text-text">{data.label}</div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

const OPS: Record<string, string> = { eq: "=", neq: "≠", contains: "contém", exists: "existe", not_exists: "não existe" };

function ConditionNode({ data, selected }: NodeProps<Node<NodeData>>) {
  const c = data.kind === "condition" ? data : null;
  return (
    <div className={cn("w-56 rounded-lg border border-dashed bg-surface-2 px-3 py-2 text-xs", selected ? "border-amber" : "border-amber/60")}>
      <Handle type="target" position={Position.Top} />
      <div className="flex items-center gap-1 text-amber"><GitBranch className="h-3.5 w-3.5" /> CONDIÇÃO</div>
      <div className="mt-0.5 text-[12.5px] text-text">
        {c?.conditions.length ? c.conditions.map((x) => `${x.field} ${OPS[x.op] ?? x.op} ${x.op.includes("exists") ? "" : String(x.value ?? "")}`).join(" e ") : "Sem regras"}
      </div>
      <div className="text-[11px] text-muted">se não: {c?.on_false === "stop" ? "parar o fluxo" : "ignorar a acção seguinte"}</div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

const nodeTypes = { trigger: TriggerNode, step: StepNode, condition: ConditionNode };

function ConditionsEditor({ value, onChange }: { value: AutomationCondition[]; onChange: (v: AutomationCondition[]) => void }) {
  return (
    <div className="flex flex-col gap-1.5">
      {value.map((c, i) => (
        <div key={i} className="flex gap-1.5">
          <Input aria-label="Campo" value={c.field} onChange={(e) => onChange(value.map((x, j) => (j === i ? { ...x, field: e.target.value } : x)))} />
          <Select aria-label="Operador" className="w-28" value={c.op} onChange={(e) => onChange(value.map((x, j) => (j === i ? { ...x, op: e.target.value } : x)))}>
            {Object.entries(OPS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
          <Input aria-label="Valor" value={String(c.value ?? "")} onChange={(e) => onChange(value.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)))} />
          <Button size="icon" variant="ghost" aria-label="Remover regra" onClick={() => onChange(value.filter((_, j) => j !== i))}><Trash2 className="h-3.5 w-3.5" /></Button>
        </div>
      ))}
      <Button size="sm" variant="ghost" onClick={() => onChange([...value, { field: "trigger.title", op: "contains", value: "" }])} icon={<Plus className="h-3.5 w-3.5" />}>Regra</Button>
      <p className="text-[11px] text-muted">Campos: <code className="font-mono">trigger.*</code> (dados do gatilho), <code className="font-mono">steps.&lt;id&gt;.*</code> (resultado de etapas anteriores). Todas as regras têm de ser verdadeiras.</p>
    </div>
  );
}

function WebhookInfo({ automationId }: { automationId?: string }) {
  const [info, setInfo] = useState<{ url: string; secret: string; example: string } | null>(null);
  const gen = useApiMutation(() => api.post<{ url: string; secret: string; example: string }>(`/api/automations/${automationId}/webhook`), {
    success: "Segredo gerado. Guarde-o agora: não volta a ser mostrado.",
    onSuccess: setInfo,
  });
  if (!automationId) return <p className="text-[12px] text-muted">Guarde a automação para gerar o endereço do webhook.</p>;
  return (
    <div className="flex flex-col gap-2 text-[12px]">
      <p className="text-muted">Outras aplicações deste Mac (scripts, n8n, atalhos, formulários) podem activar o fluxo com um POST JSON. O conteúdo fica em <code className="font-mono">trigger.*</code>.</p>
      <Button size="sm" variant="secondary" loading={gen.isPending} icon={<KeyRound className="h-3.5 w-3.5" />} onClick={() => gen.mutate(undefined)}>
        {info ? "Gerar novo segredo" : "Gerar endereço e segredo"}
      </Button>
      {info && (
        <div className="rounded-md border border-line bg-bg-2 p-2">
          <div className="break-all font-mono text-[11px]">{info.url}</div>
          <div className="mt-1 break-all font-mono text-[11px] text-amber">X-UANJI-Secret: {info.secret}</div>
          <Button size="sm" variant="ghost" className="mt-1" icon={<Copy className="h-3 w-3" />} onClick={() => void navigator.clipboard?.writeText(info.example).then(() => toast.success("Exemplo copiado."))}>Copiar exemplo curl</Button>
        </div>
      )}
    </div>
  );
}

function fieldType(prop: ActionSpec["schema"]["properties"][string]): { type: string; enum?: string[] } {
  if (prop.enum) return { type: "enum", enum: prop.enum };
  if (prop.anyOf) {
    const first = (prop.anyOf as { type?: string; enum?: string[] }[]).find((x) => x.type !== "null");
    if (first?.enum) return { type: "enum", enum: first.enum };
    return { type: first?.type ?? "string" };
  }
  return { type: prop.type ?? "string" };
}

function ParamsForm({ spec, step, onChange }: { spec: ActionSpec; step: AutomationStep; onChange: (p: Record<string, unknown>) => void }) {
  const props = spec.schema.properties;
  const required = new Set(spec.schema.required ?? []);
  return (
    <div className="flex flex-col gap-2.5">
      {Object.entries(props).map(([name, prop]) => {
        const ft = fieldType(prop);
        const value = step.params[name];
        const id = `param-${step.id}-${name}`;
        const label = `${prop.title ?? name}${required.has(name) ? " *" : ""}`;
        if (ft.type === "boolean") {
          return <Checkbox key={name} checked={value === undefined ? Boolean(prop.default) : Boolean(value)} onChange={(v) => onChange({ ...step.params, [name]: v })} label={label} />;
        }
        if (ft.type === "enum") {
          return (
            <Field key={name} label={label} htmlFor={id}>
              <Select id={id} value={String(value ?? prop.default ?? "")} onChange={(e) => onChange({ ...step.params, [name]: e.target.value })}>
                {ft.enum!.map((v) => <option key={v} value={v}>{v}</option>)}
              </Select>
            </Field>
          );
        }
        if (ft.type === "integer") {
          return (
            <Field key={name} label={label} htmlFor={id}>
              <Input id={id} inputMode="numeric" value={value === undefined || value === null ? "" : String(value)} onChange={(e) => {
                const raw = e.target.value;
                const next = { ...step.params };
                if (raw === "") delete next[name];
                else next[name] = /^\d+$/.test(raw) ? Number(raw) : raw;
                onChange(next);
              }} />
            </Field>
          );
        }
        const long = name === "content" || name === "description" || name === "body";
        return (
          <Field key={name} label={label} htmlFor={id} hint={name.endsWith("_id") ? "Pode usar {{trigger.task_id}} ou {{steps.s1.task_id}}" : undefined}>
            {long ? (
              <Textarea id={id} rows={3} value={String(value ?? "")} onChange={(e) => onChange({ ...step.params, [name]: e.target.value })} />
            ) : (
              <Input id={id} value={String(value ?? "")} onChange={(e) => {
                const next = { ...step.params, [name]: e.target.value };
                if (e.target.value === "" && !required.has(name)) delete next[name];
                onChange(next);
              }} />
            )}
          </Field>
        );
      })}
      <p className="text-[11px] text-muted">
        Modelos disponíveis: <code className="font-mono">{"{{trigger.title}}"}</code>, <code className="font-mono">{"{{steps.<id>.<campo>}}"}</code>, <code className="font-mono">{"{{now.date}}"}</code>. Substituição de texto apenas — nunca avaliação de código.
      </p>
      {!spec.reversible && spec.mutates && <p className="text-[11px] text-amber">Esta acção altera dados e não é revertida automaticamente se uma etapa posterior falhar.</p>}
    </div>
  );
}

function TriggerForm({ def, onChange, automationId }: { def: AutomationDefinition; onChange: (d: AutomationDefinition) => void; automationId?: string }) {
  const projects = useProjects();
  const t = def.trigger;
  const cfg = t.config as Record<string, unknown>;
  const set = (config: Record<string, unknown>) => onChange({ ...def, trigger: { ...t, config } });
  return (
    <div className="flex flex-col gap-2.5">
      <Field label="Tipo de gatilho" htmlFor="trg-type">
        <Select id="trg-type" value={t.type} onChange={(e) => {
          const type = e.target.value as AutomationDefinition["trigger"]["type"];
          const config =
            type === "schedule" ? { mode: "daily", time: "18:00", weekdays: [0, 1, 2, 3, 4] }
            : type === "deadline_approaching" ? { hours: 24 }
            : type === "github" ? { repo_url: "https://github.com/", event: "push", branch: "" }
            : type === "app_opened" ? { app: "" }
            : {};
          onChange({ ...def, trigger: { type, config } });
        }}>
          {Object.entries(TRIGGER_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </Select>
      </Field>
      {t.type === "schedule" && (
        <>
          <Field label="Modo" htmlFor="trg-mode">
            <Select id="trg-mode" value={String(cfg.mode ?? "daily")} onChange={(e) => set(e.target.value === "interval" ? { mode: "interval", minutes: 60 } : e.target.value === "once" ? { mode: "once", at: new Date(Date.now() + 3600_000).toISOString() } : { mode: "daily", time: "18:00", weekdays: [0, 1, 2, 3, 4] })}>
              <option value="daily">Diária a uma hora</option>
              <option value="interval">Intervalo</option>
              <option value="once">Uma vez</option>
            </Select>
          </Field>
          {cfg.mode === "interval" && (
            <Field label="Minutos (mín. 15)" htmlFor="trg-min"><Input id="trg-min" inputMode="numeric" value={String(cfg.minutes ?? "")} onChange={(e) => set({ ...cfg, minutes: Number(e.target.value) || e.target.value })} /></Field>
          )}
          {cfg.mode === "daily" && (
            <>
              <Field label="Hora (local)" htmlFor="trg-time"><Input id="trg-time" type="time" value={String(cfg.time ?? "18:00")} onChange={(e) => set({ ...cfg, time: e.target.value })} /></Field>
              <div className="flex flex-wrap gap-2">
                {["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"].map((d, i) => {
                  const days = (cfg.weekdays as number[] | undefined) ?? [];
                  return <Checkbox key={d} checked={days.includes(i)} onChange={(v) => set({ ...cfg, weekdays: v ? [...days, i].sort() : days.filter((x) => x !== i) })} label={d} />;
                })}
              </div>
            </>
          )}
          {cfg.mode === "once" && (
            <Field label="Data e hora" htmlFor="trg-at"><Input id="trg-at" type="datetime-local" onChange={(e) => set({ ...cfg, at: new Date(e.target.value).toISOString() })} /></Field>
          )}
        </>
      )}
      {(t.type === "task_completed" || t.type === "deadline_approaching") && (
        <Field label="Apenas do projecto" htmlFor="trg-proj">
          <Select id="trg-proj" value={String(cfg.project_id ?? "")} onChange={(e) => set({ ...cfg, project_id: e.target.value || null })}>
            <option value="">Qualquer projecto</option>
            {projects.data?.items.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </Select>
        </Field>
      )}
      {t.type === "deadline_approaching" && (
        <Field label="Horas antes do prazo (1–168)" htmlFor="trg-h"><Input id="trg-h" inputMode="numeric" value={String(cfg.hours ?? 24)} onChange={(e) => set({ ...cfg, hours: Number(e.target.value) || e.target.value })} /></Field>
      )}
      {t.type === "webhook" && <WebhookInfo automationId={automationId} />}
      {t.type === "github" && (
        <>
          <Field label="Repositório" htmlFor="trg-repo"><Input id="trg-repo" value={String(cfg.repo_url ?? "")} onChange={(e) => set({ ...cfg, repo_url: e.target.value })} placeholder="https://github.com/dono/repositorio" /></Field>
          <Field label="Evento" htmlFor="trg-ev">
            <Select id="trg-ev" value={String(cfg.event ?? "push")} onChange={(e) => set({ ...cfg, event: e.target.value })}>
              <option value="push">Novo commit</option><option value="pr_opened">Pull request aberto/actualizado</option><option value="pr_merged">Pull request integrado (merge)</option><option value="issue_opened">Nova issue</option><option value="release">Nova release</option>
            </Select>
          </Field>
          {cfg.event === "push" && <Field label="Branch (opcional)" htmlFor="trg-br"><Input id="trg-br" value={String(cfg.branch ?? "")} onChange={(e) => set({ ...cfg, branch: e.target.value })} placeholder="main" /></Field>}
          <p className="text-[11px] text-muted">Verificado de 5 em 5 minutos (configure um token GitHub em Integrações para repositórios privados). Campos: trigger.sha, trigger.message, trigger.title, trigger.number, trigger.url.</p>
        </>
      )}
      {t.type === "app_opened" && (
        <>
          <Field label="Aplicação" htmlFor="trg-app" hint="Ex.: Xcode, Visual Studio Code, Figma"><Input id="trg-app" value={String(cfg.app ?? "")} onChange={(e) => set({ ...cfg, app: e.target.value })} /></Field>
          <p className="text-[11px] text-muted">Requer o monitor de actividade ligado. No máximo uma execução a cada 30 minutos.</p>
        </>
      )}
      <div className="hud-label mt-2">Condições do fluxo inteiro</div>
      <ConditionsEditor value={def.conditions} onChange={(conditions) => onChange({ ...def, conditions })} />
    </div>
  );
}

function RunDialog({ runId, onClose }: { runId: string; onClose: () => void }) {
  const { data, isLoading } = useRun(runId);
  const cancel = useApiMutation(() => api.post(`/api/automation-runs/${runId}/cancel`), { invalidate: [["runs"], ["automations"]], success: "Cancelamento pedido." });
  return (
    <Dialog open onClose={onClose} title="Detalhe da execução" wide footer={data && (data.status === "running" || data.status === "pending") ? <Button variant="danger" onClick={() => cancel.mutate(undefined)} icon={<Ban className="h-3.5 w-3.5" />}>Cancelar execução</Button> : undefined}>
      {isLoading || !data ? <Loading /> : (
        <div className="flex flex-col gap-3 text-[13px]">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={RUN_TONE[data.status]}>{RUN_LABEL[data.status]}</Badge>
            <span className="text-muted">v{data.version} · {TRIGGER_LABEL[data.trigger] ?? data.trigger} · {fmtDateTime(data.started_at)} · {data.duration_ms ?? "—"} ms</span>
          </div>
          {data.error && <p className="rounded border border-danger/30 bg-danger/5 p-2 text-danger">{data.error}</p>}
          <ol className="flex flex-col gap-2">
            {data.steps?.map((s) => (
              <li key={s.index} className="rounded-md border border-line p-2.5">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-muted">#{s.index + 1} {s.node_id}</span>
                  <span>{s.action}</span>
                  <Badge tone={RUN_TONE[s.status] ?? "neutral"}>{s.status}</Badge>
                  {s.attempts > 1 && <span className="text-xs text-amber">{s.attempts} tentativas</span>}
                </div>
                {s.error && <p className="mt-1 text-xs text-danger">{s.error}</p>}
                <details className="mt-1 text-xs text-muted">
                  <summary className="cursor-pointer">Entrada / saída</summary>
                  <pre className="mt-1 overflow-auto whitespace-pre-wrap font-mono text-[11px]">{JSON.stringify({ input: s.input, output: s.output }, null, 2)}</pre>
                </details>
              </li>
            ))}
            {data.steps?.length === 0 && <li className="text-xs text-muted">Nenhuma etapa executada (condições não satisfeitas ou cancelada).</li>}
          </ol>
        </div>
      )}
    </Dialog>
  );
}

export default function AutomationEditorPage() {
  const { id } = useParams();
  const isNew = id === "new";
  const navigate = useNavigate();
  const existing = useAutomation(id);
  const catalog = useActionCatalog();
  const runs = useAutomationRuns(id);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [def, setDef] = useState<AutomationDefinition>(EMPTY);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<NodeData>>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selected, setSelected] = useState<string>(TRIGGER_ID);
  const [errors, setErrors] = useState<{ path: string; message: string; step?: string }[]>([]);
  const [side, setSide] = useState<"node" | "runs" | "versions">("node");
  const [openRun, setOpenRun] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const specs = useMemo(() => new Map((catalog.data ?? []).map((s) => [s.name, s])), [catalog.data]);

  const toFlow = (d: AutomationDefinition) => {
    const g = graphFromDefinition(d);
    setNodes(g.nodes.map((n) => ({ ...n, type: n.data.kind, data: { ...n.data } })) as Node<NodeData>[]);
    setEdges(g.edges);
  };

  useEffect(() => {
    if (loaded) return;
    if (isNew) {
      setName("Nova automação");
      toFlow(EMPTY);
      setLoaded(true);
    } else if (existing.data) {
      const a: Automation = existing.data;
      setName(a.name);
      setDescription(a.description);
      setEnabled(a.enabled);
      setDef(a.definition);
      toFlow(a.definition);
      setLoaded(true);
    }
  }, [existing.data, isNew, loaded]);

  // Etiquetas e destaque de erros nos nós
  const errorSteps = new Set(errors.map((e) => e.step).filter(Boolean));
  const viewNodes = nodes.map((n) => ({
    ...n,
    data: {
      ...n.data,
      label: n.data.kind === "trigger" ? TRIGGER_LABEL[def.trigger.type] : n.data.kind === "step" ? specs.get(n.data.step.action)?.label ?? n.data.step.action : "",
      error: n.data.kind === "step" && errorSteps.has(n.data.step.id),
      result: n.data.kind === "step" && specs.get(n.data.step.action)?.category === "result",
    },
  }));

  const updateStep = (stepId: string, patch: Partial<AutomationStep>) =>
    setNodes((ns) => ns.map((n) => (n.id === stepId && n.data.kind === "step" ? { ...n, data: { ...n.data, step: { ...n.data.step, ...patch } } } : n)));

  const updateCondition = (cid: string, patch: Partial<ConditionData>) =>
    setNodes((ns) => ns.map((n) => (n.id === cid && n.data.kind === "condition" ? { ...n, data: { ...n.data, ...patch } } : n)));

  // Último nó da cadeia (acção ou condição), para ligar o novo nó a seguir.
  const tail = () => {
    const out = new Map(edges.map((e) => [e.source, e.target]));
    let cur = TRIGGER_ID;
    const seen = new Set<string>();
    while (out.get(cur) && !seen.has(cur)) {
      seen.add(cur);
      cur = out.get(cur)!;
    }
    return cur;
  };

  const addCondition = () => {
    const cid = nextStepId(nodes as unknown as FlowNode[], "c");
    const last = tail();
    const lastNode = nodes.find((n) => n.id === last);
    setNodes((ns) => [...ns, { id: cid, type: "condition", position: { x: lastNode?.position.x ?? 0, y: (lastNode?.position.y ?? 0) + 120 }, data: { kind: "condition", conditions: [{ field: "trigger.title", op: "contains", value: "" }], on_false: "skip" } }]);
    setEdges((es) => [...es, { id: `e-${last}-${cid}`, source: last, target: cid }]);
    setSelected(cid);
    setSide("node");
  };

  const addStep = (action: string) => {
    const sid = nextStepId(nodes as unknown as FlowNode[]);
    const last = tail();
    const lastNode = nodes.find((n) => n.id === last);
    const spec = specs.get(action);
    const defaults: Record<string, unknown> = {};
    for (const [k, p] of Object.entries(spec?.schema.properties ?? {})) if (p.default !== undefined && p.default !== null) defaults[k] = p.default;
    setNodes((ns) => [...ns, { id: sid, type: "step", position: { x: lastNode?.position.x ?? 0, y: (lastNode?.position.y ?? 0) + 120 }, data: { kind: "step", step: { id: sid, action, params: defaults } } }]);
    setEdges((es) => [...es, { id: `e-${last}-${sid}`, source: last, target: sid }]);
    setSelected(sid);
    setSide("node");
  };

  const removeStep = (sid: string) => {
    setNodes((ns) => ns.filter((n) => n.id !== sid));
    setEdges((es) => {
      const inbound = es.find((e) => e.target === sid);
      const outbound = es.find((e) => e.source === sid);
      const rest = es.filter((e) => e.source !== sid && e.target !== sid);
      return inbound && outbound ? [...rest, { id: `e-${inbound.source}-${outbound.target}`, source: inbound.source, target: outbound.target }] : rest;
    });
    setSelected(TRIGGER_ID);
  };

  const buildDefinition = (): AutomationDefinition | null => {
    const chain = chainFromGraph(nodes as unknown as FlowNode[], edges as FlowEdge[]);
    if (chain.errors.length) {
      setErrors(chain.errors.map((m) => ({ path: "fluxo", message: m })));
      return null;
    }
    const positions = Object.fromEntries(nodes.map((n) => [n.id, n.position]));
    return { ...def, steps: chain.steps, ui: { positions } };
  };

  const save = useApiMutation(
    async () => {
      const d = buildDefinition();
      if (!d) throw new Error("O fluxo tem erros. Corrija-os antes de guardar.");
      const v = await api.post<{ valid: boolean; errors: { path: string; message: string; step?: string }[] }>("/api/automations/validate", d);
      if (!v.valid) {
        setErrors(v.errors);
        throw new Error("A validação falhou. Veja os erros indicados.");
      }
      setErrors([]);
      const body = { name, description, definition: d, enabled };
      try {
        return await (isNew ? api.post<Automation>("/api/automations", body) : api.patch<Automation>(`/api/automations/${id}`, body));
      } catch (e) {
        if (e instanceof ApiError && Array.isArray(e.details.errors)) setErrors(e.details.errors as typeof errors);
        throw e;
      }
    },
    {
      invalidate: [["automations"]],
      success: (a) => `Guardado (versão ${a.version}).`,
      onSuccess: (a) => {
        if (isNew) navigate(`/automations/${a.id}`, { replace: true });
      },
    },
  );
  const run = useRunAutomation((r) => setOpenRun(r.id));
  const rollback = useApiMutation((version: number) => api.post<Automation>(`/api/automations/${id}/rollback`, { version }), {
    invalidate: [["automations"]],
    success: (a) => `Reposta como versão ${a.version}.`,
    onSuccess: (a) => {
      setDef(a.definition);
      toFlow(a.definition);
    },
  });
  const del = useApiMutation(() => api.del(`/api/automations/${id}`, { confirm: true }), { invalidate: [["automations"]], success: "Automação eliminada.", onSuccess: () => navigate("/automations") });
  const versions = useApiMutation(() => api.get<{ version: number; created_at: string }[]>(`/api/automations/${id}/versions`), { silentError: true });

  if (!isNew && existing.isLoading) return <Loading />;
  if (!isNew && existing.error) return <ErrorState error={existing.error} />;
  const sel = viewNodes.find((n) => n.id === selected);
  const selStep = sel && sel.data.kind === "step" ? sel.data.step : null;
  const selCond = sel && sel.data.kind === "condition" ? sel.data : null;
  const selSpec = selStep ? specs.get(selStep.action) : undefined;
  const dirtyNote = existing.data && existing.data.version ? `v${existing.data.version}` : "nova";

  return (
    <div className="mx-auto flex max-w-[1600px] flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Input aria-label="Nome da automação" className="h-10 max-w-md text-base font-semibold" value={name} onChange={(e) => setName(e.target.value)} />
        <Badge tone="primary">{dirtyNote}</Badge>
        <Checkbox checked={enabled} onChange={setEnabled} label="Activa (gatilhos automáticos)" />
        <div className="ml-auto flex gap-2">
          {!isNew && <Button loading={run.isPending} onClick={() => run.mutate(id!)} icon={<Play className="h-3.5 w-3.5" />}>Executar agora</Button>}
          <Button variant="primary" loading={save.isPending} onClick={() => save.mutate(undefined)} icon={<Save className="h-3.5 w-3.5" />}>Validar e guardar</Button>
          {!isNew && <Button variant="danger" size="icon" aria-label="Eliminar automação" onClick={() => setConfirmDelete(true)}><Trash2 className="h-4 w-4" /></Button>}
        </div>
      </div>
      <Input aria-label="Descrição" placeholder="Descrição" value={description} onChange={(e) => setDescription(e.target.value)} />
      {errors.length > 0 && (
        <div role="alert" className="rounded-md border border-danger/40 bg-danger/5 p-2.5 text-xs text-danger">
          <ul className="list-disc pl-4">{errors.map((e, i) => <li key={i}>{e.step ? `[${e.step}] ` : ""}{e.path}: {e.message}</li>)}</ul>
        </div>
      )}
      {!isNew && existing.data?.last_run?.status === "failed" && <p className="text-xs text-danger">Última execução falhou: {existing.data.last_run.error}</p>}
      <div className="grid gap-3 lg:grid-cols-[1fr_360px]">
        <div className="hud-panel overflow-hidden" style={{ height: "66vh" }}>
          <ReactFlow
            nodes={viewNodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={(c: Connection) => setEdges((es) => addEdge({ ...c, id: `e-${c.source}-${c.target}` }, es))}
            onNodeClick={(_, n) => { setSelected(n.id); setSide("node"); }}
            deleteKeyCode={null}
            fitView
            colorMode="dark"
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={28} color="rgb(120 170 220 / 0.12)" />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>
        <div className="flex flex-col gap-3">
          <Panel title="Adicionar nó">
            <div className="grid grid-cols-1 gap-1.5">
              <button type="button" onClick={addCondition} className="rounded-md border border-dashed border-amber/60 px-2.5 py-1.5 text-left text-xs hover:bg-surface-3">
                <span className="flex items-center gap-1 text-amber"><GitBranch className="h-3.5 w-3.5" /> Condição</span>
                <span className="block text-[11px] text-muted">Só continua para a acção seguinte se as regras forem verdadeiras.</span>
              </button>
              <div className="hud-label mt-1">Acções</div>
              {catalog.data?.filter((a) => a.category !== "result").map((a) => (
                <button key={a.name} type="button" onClick={() => addStep(a.name)} className="rounded-md border border-line px-2.5 py-1.5 text-left text-xs hover:border-primary/50 hover:bg-surface-3">
                  <span className="text-text">{a.label}</span>
                  <span className="block text-[11px] text-muted">{a.description}</span>
                </button>
              ))}
              <div className="hud-label mt-1">Resultados</div>
              {catalog.data?.filter((a) => a.category === "result").map((a) => (
                <button key={a.name} type="button" onClick={() => addStep(a.name)} className="rounded-md border border-success/40 px-2.5 py-1.5 text-left text-xs hover:bg-surface-3">
                  <span className="text-success">{a.label}</span>
                  <span className="block text-[11px] text-muted">{a.description}</span>
                </button>
              ))}
            </div>
          </Panel>
          <Panel
            title={<Tabs value={side} onChange={(v) => { setSide(v); if (v === "versions" && !isNew) versions.mutate(undefined); }} items={[
              { value: "node", label: "Configuração" },
              { value: "runs", label: "Execuções" },
              { value: "versions", label: "Versões" },
            ]} />}
          >
            {side === "node" && (selCond ? (
              <div className="flex flex-col gap-2.5">
                <div className="flex items-center justify-between">
                  <span className="flex items-center gap-1 text-[13px] font-medium text-amber"><GitBranch className="h-4 w-4" /> Condição <span className="font-mono text-xs text-muted">({selected})</span></span>
                  <Button size="sm" variant="ghost" onClick={() => removeStep(selected)} icon={<Trash2 className="h-3.5 w-3.5" />}>Remover</Button>
                </div>
                <ConditionsEditor value={selCond.conditions} onChange={(conditions) => updateCondition(selected, { conditions })} />
                <Field label="Se as regras não se verificarem" htmlFor="cond-false">
                  <Select id="cond-false" value={selCond.on_false} onChange={(e) => updateCondition(selected, { on_false: e.target.value as "skip" | "stop" })}>
                    <option value="skip">Ignorar a acção seguinte e continuar</option>
                    <option value="stop">Parar o fluxo aqui</option>
                  </Select>
                </Field>
              </div>
            ) : selected === TRIGGER_ID || !selStep ? (
              <TriggerForm def={def} onChange={setDef} automationId={isNew ? undefined : id} />
            ) : selSpec ? (
              <div>
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-[13px] font-medium">{selSpec.label} <span className="font-mono text-xs text-muted">({selStep.id})</span></span>
                  <Button size="sm" variant="ghost" onClick={() => removeStep(selStep.id)} icon={<Trash2 className="h-3.5 w-3.5" />}>Remover</Button>
                </div>
                <ParamsForm spec={selSpec} step={selStep} onChange={(params) => updateStep(selStep.id, { params })} />
              </div>
            ) : <Loading />)}
            {side === "runs" && (isNew ? <p className="text-xs text-muted">Guarde a automação primeiro.</p> : (
              <ul className="flex flex-col">
                {runs.data?.map((r) => (
                  <li key={r.id}>
                    <button type="button" className="flex w-full items-center gap-2 border-b border-line/60 py-1.5 text-left text-xs hover:bg-surface-3" onClick={() => setOpenRun(r.id)}>
                      <Badge tone={RUN_TONE[r.status]}>{RUN_LABEL[r.status]}</Badge>
                      <span className="text-text-2">{TRIGGER_LABEL[r.trigger] ?? r.trigger}</span>
                      <span className="ml-auto text-muted">{fmtDateTime(r.started_at)}</span>
                    </button>
                  </li>
                ))}
                {runs.data?.length === 0 && <li className="text-xs text-muted">Sem execuções.</li>}
              </ul>
            ))}
            {side === "versions" && (isNew ? <p className="text-xs text-muted">Sem versões.</p> : versions.isPending ? <Loading /> : versions.isError ? <p className="text-xs text-danger">{errorMessage(versions.error)}</p> : (
              <ul className="flex flex-col">
                {versions.data?.map((v) => (
                  <li key={v.version} className="flex items-center gap-2 border-b border-line/60 py-1.5 text-xs">
                    <span className="font-mono">v{v.version}</span>
                    <span className="text-muted">{fmtDateTime(v.created_at)}</span>
                    {v.version !== existing.data?.version && <Button size="sm" variant="ghost" className="ml-auto" onClick={() => rollback.mutate(v.version)}>Repor</Button>}
                  </li>
                ))}
              </ul>
            ))}
          </Panel>
        </div>
      </div>
      {openRun && <RunDialog runId={openRun} onClose={() => setOpenRun(null)} />}
      <ConfirmDialog open={confirmDelete} title="Eliminar automação" message="A automação e todo o histórico de execuções serão eliminados." confirmLabel="Eliminar" loading={del.isPending} onConfirm={() => del.mutate(undefined)} onCancel={() => setConfirmDelete(false)} />
    </div>
  );
}
