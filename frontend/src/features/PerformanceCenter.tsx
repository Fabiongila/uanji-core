import { Flag, Plus, Target, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { useApiMutation, useProjects } from "@/api/hooks";
import { ChartOrTable, Legend, SimpleBars, TrendArea } from "@/components/charts";
import { Badge, Button, ConfirmDialog, Dialog, ErrorState, Field, Input, Loading, Panel, Progress, Select, Tabs } from "@/components/ui";
import { Stat } from "@/features/common";

export interface Goal {
  id: string;
  title: string;
  description: string;
  project_id: string | null;
  project_name: string | null;
  target_date: string | null;
  status: "active" | "achieved" | "dropped";
  tasks_total: number;
  tasks_done: number;
  percent: number | null;
}

type Stats = { count: number; avg_h: number | null; median_h: number | null; p85_h: number | null };
interface Center {
  cycle_time: Stats;
  lead_time: Stats;
  cycle_missing: number;
  blocked: { now: number; items: { id: string; number: number | null; title: string; reason: string; hours: number | null }[]; total_hours_in_done: number };
  interruptions: { short_focus: number; focus_sessions: number; regressions: number; per_day: number; app_switches_per_hour: number | null; monitor_data: boolean; app_switches_scope?: string };
  goals: Goal[];
  weekly: { week: string; label: string; done: number; created: number; cycle_avg_h: number | null; blocked_h: number; focus_h: number; interruptions: number; switches_per_hour: number | null }[];
  trend: { done_delta: number; cycle_delta_h: number | null };
  sources: Record<string, string>;
}

export const useGoals = () => useQuery({ queryKey: ["goals"], queryFn: () => api.get<Goal[]>("/api/goals") });

function dur(h: number | null): string {
  if (h == null) return "—";
  if (h < 1) return `${Math.round(h * 60)} min`;
  if (h < 48) return `${h.toFixed(1).replace(".", ",")} h`;
  return `${(h / 24).toFixed(1).replace(".", ",")} d`;
}

function GoalDialog({ goal, onClose }: { goal: Goal | null; onClose: () => void }) {
  const projects = useProjects();
  const [f, setF] = useState({
    title: goal?.title ?? "",
    description: goal?.description ?? "",
    project_id: goal?.project_id ?? "",
    target_date: goal?.target_date ?? "",
    status: goal?.status ?? "active",
  });
  const save = useApiMutation(
    () => {
      const body = { ...f, project_id: f.project_id || null, target_date: f.target_date || null };
      return goal ? api.put<Goal>(`/api/goals/${goal.id}`, body) : api.post<Goal>("/api/goals", body);
    },
    { invalidate: [["goals"], ["performance"]], success: "Objectivo guardado.", onSuccess: onClose },
  );
  return (
    <Dialog
      open
      onClose={onClose}
      title={goal ? "Editar objectivo" : "Novo objectivo"}
      footer={<Button variant="primary" loading={save.isPending} disabled={!f.title.trim()} onClick={() => save.mutate(undefined)}>Guardar</Button>}
    >
      <div className="flex flex-col gap-3">
        <Field label="Objectivo" htmlFor="g-t"><Input id="g-t" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder="Ex.: API pública v1 em produção" /></Field>
        <Field label="Projecto (opcional)" htmlFor="g-p">
          <Select id="g-p" value={f.project_id} onChange={(e) => setF({ ...f, project_id: e.target.value })}>
            <option value="">Vários projectos / pessoal</option>
            {projects.data?.items.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </Select>
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Data-alvo" htmlFor="g-d"><Input id="g-d" type="date" value={f.target_date} onChange={(e) => setF({ ...f, target_date: e.target.value })} /></Field>
          <Field label="Estado" htmlFor="g-s">
            <Select id="g-s" value={f.status} onChange={(e) => setF({ ...f, status: e.target.value as Goal["status"] })}>
              <option value="active">Activo</option><option value="achieved">Alcançado</option><option value="dropped">Abandonado</option>
            </Select>
          </Field>
        </div>
        <p className="text-[11px] text-muted">O progresso é a fracção das tarefas ligadas que está concluída. Ligue tarefas ao objectivo no detalhe de cada tarefa.</p>
      </div>
    </Dialog>
  );
}

export function GoalsPanel({ goals }: { goals: Goal[] }) {
  const [edit, setEdit] = useState<Goal | null | "new">(null);
  const [del, setDel] = useState<Goal | null>(null);
  const remove = useApiMutation((g: Goal) => api.del(`/api/goals/${g.id}`), { invalidate: [["goals"], ["performance"]], success: "Objectivo eliminado.", onSuccess: () => setDel(null) });
  return (
    <Panel title="Progresso por objectivo" actions={<Button size="sm" variant="ghost" icon={<Plus className="h-3.5 w-3.5" />} onClick={() => setEdit("new")}>Objectivo</Button>}>
      {goals.length === 0 ? (
        <p className="text-[13px] text-muted">Sem objectivos activos. Crie um e ligue-lhe tarefas para medir o progresso real.</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {goals.map((g) => (
            <li key={g.id}>
              <div className="flex items-center gap-2 text-[13px]">
                <Target className="h-3.5 w-3.5 text-primary" />
                <button type="button" className="text-left text-text hover:text-primary" onClick={() => setEdit(g)}>{g.title}</button>
                {g.project_name && <Badge>{g.project_name}</Badge>}
                {g.target_date && <span className="text-[11px] text-muted">até {g.target_date.split("-").reverse().join("/")}</span>}
                <span className="ml-auto font-mono text-xs">{g.percent == null ? "sem tarefas" : `${g.percent}% · ${g.tasks_done}/${g.tasks_total}`}</span>
                <Button size="icon" variant="ghost" aria-label={`Eliminar ${g.title}`} onClick={() => setDel(g)}><Trash2 className="h-3.5 w-3.5" /></Button>
              </div>
              <div className="mt-1"><Progress value={g.percent} tone={g.percent === 100 ? "success" : "primary"} /></div>
            </li>
          ))}
        </ul>
      )}
      {edit && <GoalDialog goal={edit === "new" ? null : edit} onClose={() => setEdit(null)} />}
      <ConfirmDialog open={!!del} title="Eliminar objectivo" message="As tarefas ligadas mantêm-se, apenas deixam de estar associadas a este objectivo." confirmLabel="Eliminar" loading={remove.isPending} onConfirm={() => del && remove.mutate(del)} onCancel={() => setDel(null)} />
    </Panel>
  );
}

export function PerformanceCenter() {
  const [weeks, setWeeks] = useState<"4" | "8" | "12">("8");
  const projects = useProjects();
  const [projectId, setProjectId] = useState("");
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["performance", weeks, projectId],
    queryFn: () => api.get<Center>("/api/performance", { weeks, project_id: projectId || undefined }),
  });
  if (isLoading) return <Loading label="A calcular o centro de desempenho…" />;
  if (error || !data) return <ErrorState error={error} onRetry={() => void refetch()} />;
  const i = data.interruptions;
  const weeklyRows = data.weekly.map((w) => ({ ...w, cycle_avg_h: w.cycle_avg_h ?? "—", switches_per_hour: w.switches_per_hour ?? "—" }));
  return (
    <section className="flex flex-col gap-4" aria-label="Centro de desempenho">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="hud-label text-primary">Centro de desempenho</h2>
        <Select aria-label="Projecto" className="ml-auto w-56" value={projectId} onChange={(e) => setProjectId(e.target.value)}>
          <option value="">Todos os projectos</option>
          {projects.data?.items.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </Select>
        <Tabs value={weeks} onChange={setWeeks} items={[{ value: "4", label: "4 semanas" }, { value: "8", label: "8 semanas" }, { value: "12", label: "12 semanas" }]} />
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat label="Tempo de ciclo (média)" value={dur(data.cycle_time.avg_h)} sub={`mediana ${dur(data.cycle_time.median_h)} · 85% até ${dur(data.cycle_time.p85_h)}`} tone="primary" />
        <Stat label="Criação → conclusão" value={dur(data.lead_time.avg_h)} sub={`${data.lead_time.count} tarefa(s) concluída(s)`} tone="neutral" />
        <Stat label="Bloqueadas agora" value={data.blocked.now} sub={`${dur(data.blocked.total_hours_in_done)} bloqueadas nas concluídas`} tone={data.blocked.now ? "danger" : "neutral"} to="/tasks?status=blocked" />
        <Stat label="Interrupções / dia" value={String(i.per_day).replace(".", ",")} sub={`${i.short_focus} focos curtos · ${i.regressions} recuos`} tone={i.per_day >= 2 ? "amber" : "neutral"} />
        <Stat label="Mudanças de app / hora" value={i.app_switches_per_hour == null ? "—" : String(i.app_switches_per_hour).replace(".", ",")} sub={i.app_switches_scope === "project_filter" ? "só na vista de todos os projectos" : i.monitor_data ? "monitor de actividade" : "ligue o monitor em Actividade"} tone="neutral" />
      </div>
      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <Panel title="Evolução semanal" actions={<Legend items={["Concluídas", "Criadas"]} />}>
          <ChartOrTable
            chart={<TrendArea data={weeklyRows} xKey="label" series={[{ key: "done", label: "Concluídas" }, { key: "created", label: "Criadas" }]} height={200} />}
            columns={[
              { key: "label", label: "Semana" },
              { key: "done", label: "Concluídas" },
              { key: "created", label: "Criadas" },
              { key: "cycle_avg_h", label: "Ciclo médio (h)" },
              { key: "blocked_h", label: "Bloqueado (h)" },
              { key: "focus_h", label: "Foco (h)" },
              { key: "interruptions", label: "Interrupções" },
            ]}
            rows={weeklyRows}
          />
          <p className="mt-2 text-[12px] text-text-2">
            {data.trend.done_delta === 0 ? "Mesmo número de tarefas concluídas que na semana anterior." : `${Math.abs(data.trend.done_delta)} tarefa(s) concluída(s) a ${data.trend.done_delta > 0 ? "mais" : "menos"} do que na semana anterior.`}
            {data.trend.cycle_delta_h != null && ` Ciclo médio ${data.trend.cycle_delta_h <= 0 ? "mais rápido" : "mais lento"} em ${dur(Math.abs(data.trend.cycle_delta_h))}.`}
          </p>
        </Panel>
        <Panel title="Tempo de ciclo por semana (h)">
          <SimpleBars data={data.weekly.map((w) => ({ semana: w.label, horas: w.cycle_avg_h ?? 0 }))} xKey="semana" yKey="horas" label="Horas" unit="h" height={200} />
        </Panel>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <GoalsPanel goals={data.goals} />
        <Panel title="Bloqueios actuais">
          {data.blocked.items.length === 0 ? (
            <p className="text-[13px] text-muted">Nenhuma tarefa bloqueada.</p>
          ) : (
            <ul className="flex flex-col">
              {data.blocked.items.map((b) => (
                <li key={b.id} className="flex items-start gap-2 border-b border-line/60 py-2 text-[13px] last:border-0">
                  <Flag className="mt-0.5 h-3.5 w-3.5 shrink-0 text-danger" />
                  <span className="min-w-0 flex-1">
                    <Link to={`/tasks/${b.id}`} className="text-text hover:text-primary">{b.number != null && <span className="mr-1 font-mono text-xs text-muted">UJ-{b.number}</span>}{b.title}</Link>
                    {b.reason && <span className="block text-xs text-muted">{b.reason}</span>}
                  </span>
                  <span className="shrink-0 font-mono text-xs text-danger">{dur(b.hours)}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
      <p className="text-[11px] text-muted">
        {data.sources.cycle_time} {data.sources.interruptions}
        {data.cycle_missing > 0 && ` ${data.cycle_missing} tarefa(s) concluída(s) sem passar por «em curso» não entram no tempo de ciclo.`}
      </p>
    </section>
  );
}
