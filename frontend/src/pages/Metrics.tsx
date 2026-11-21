import { Info } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useMetrics } from "@/api/hooks";
import { ChartOrTable, Legend, SimpleBars, TrendArea } from "@/components/charts";
import { ErrorState, Field, Input, Loading, PageHeader, Panel, Progress, Tabs } from "@/components/ui";
import { Stat } from "@/features/common";
import { PerformanceCenter } from "@/features/PerformanceCenter";
import { addDays, fmtMinutes, isoDay } from "@/lib/utils";

const PRESETS = { "7": 7, "30": 30, "90": 90 } as const;

export default function MetricsPage() {
  const [preset, setPreset] = useState<"7" | "30" | "90" | "custom">("30");
  const today = new Date();
  const [custom, setCustom] = useState({ start: isoDay(addDays(today, -29)), end: isoDay(today) });
  const range = preset === "custom" ? custom : { start: isoDay(addDays(today, -(PRESETS[preset] - 1))), end: isoDay(today) };
  const { data, isLoading, error, refetch } = useMetrics(range.start, range.end);

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-4">
      <PageHeader
        title="Desempenho"
        subtitle="Métricas calculadas a partir dos registos guardados. Nada é estimado ou inventado."
        actions={
          <div className="flex flex-wrap items-end gap-2">
            <Tabs value={preset} onChange={setPreset} items={[{ value: "7", label: "7 dias" }, { value: "30", label: "30 dias" }, { value: "90", label: "90 dias" }, { value: "custom", label: "Personalizado" }]} />
            {preset === "custom" && (
              <>
                <Field label="De" htmlFor="m-s"><Input id="m-s" type="date" value={custom.start} onChange={(e) => setCustom({ ...custom, start: e.target.value })} /></Field>
                <Field label="Até" htmlFor="m-e"><Input id="m-e" type="date" value={custom.end} onChange={(e) => setCustom({ ...custom, end: e.target.value })} /></Field>
              </>
            )}
          </div>
        }
      />
      <PerformanceCenter />
      <h2 className="hud-label mt-2 text-primary">Registos do período</h2>
      {isLoading ? <Loading /> : error || !data ? <ErrorState error={error} onRetry={() => void refetch()} /> : (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            <Stat label="Concluídas" value={data.totals.done} tone="success" />
            <Stat label="Criadas" value={data.totals.created} tone="neutral" />
            <Stat label="Concluídas fora do prazo" value={data.totals.late_done} tone={data.totals.late_done ? "amber" : "neutral"} />
            <Stat label="Atrasadas agora" value={data.totals.overdue_now} tone={data.totals.overdue_now ? "danger" : "neutral"} to="/tasks?due=overdue" />
            <Stat label="Foco registado" value={fmtMinutes(data.totals.focus_minutes)} tone="amber" />
          </div>
          <Panel title="Actividade diária" actions={<Legend items={["Concluídas", "Criadas"]} />}>
            <ChartOrTable
              chart={<TrendArea data={data.series.map((d) => ({ ...d, label: d.date.slice(5).split("-").reverse().join("/") }))} xKey="label" series={[{ key: "done", label: "Concluídas" }, { key: "created", label: "Criadas" }]} height={220} />}
              columns={[{ key: "date", label: "Dia" }, { key: "done", label: "Concluídas" }, { key: "created", label: "Criadas" }, { key: "focus_minutes", label: "Foco (min)" }]}
              rows={data.series}
            />
          </Panel>
          <div className="grid gap-4 lg:grid-cols-2">
            <Panel title="Tarefas concluídas por semana">
              <ChartOrTable
                chart={<SimpleBars data={data.weekly_done.map((w) => ({ ...w, label: w.week.slice(5).split("-").reverse().join("/") }))} xKey="label" yKey="done" label="Concluídas" />}
                columns={[{ key: "week", label: "Semana (segunda)" }, { key: "done", label: "Concluídas" }]}
                rows={data.weekly_done}
              />
            </Panel>
            <Panel title="Distribuição do trabalho concluído por projecto">
              {data.done_by_project.length ? (
                <ChartOrTable
                  chart={<SimpleBars data={data.done_by_project} xKey="project" yKey="done" label="Concluídas" layout="horizontal" height={Math.max(140, data.done_by_project.length * 34)} />}
                  columns={[{ key: "project", label: "Projecto" }, { key: "done", label: "Concluídas" }]}
                  rows={data.done_by_project}
                />
              ) : <p className="text-xs text-muted">Sem tarefas concluídas no período.</p>}
            </Panel>
            <Panel title="Tempo de foco registado por projecto">
              {data.focus_by_project.length ? (
                <ChartOrTable
                  chart={<SimpleBars data={data.focus_by_project} xKey="project" yKey="minutes" label="Minutos" unit="min" layout="horizontal" height={Math.max(140, data.focus_by_project.length * 34)} />}
                  columns={[{ key: "project", label: "Projecto" }, { key: "minutes", label: "Minutos" }]}
                  rows={data.focus_by_project}
                />
              ) : <p className="text-xs text-muted">Sem sessões de foco registadas no período.</p>}
            </Panel>
            <Panel title="Automações no período">
              {Object.keys(data.automation_runs).length ? (
                <ul className="flex flex-col gap-1 text-[13px]">
                  {Object.entries(data.automation_runs).map(([k, v]) => (
                    <li key={k} className="flex justify-between border-b border-line/50 py-1"><span className="text-text-2">{k}</span><span className="font-mono">{v}</span></li>
                  ))}
                </ul>
              ) : <p className="text-xs text-muted">Sem execuções no período.</p>}
            </Panel>
          </div>
          <Panel title="Progresso por projecto">
            <ul className="flex flex-col gap-2">
              {data.project_progress.map((p) => (
                <li key={p.id} className="flex items-center gap-3 text-[13px]">
                  <Link to={`/projects/${p.id}`} className="w-56 truncate text-text hover:text-primary">{p.name}</Link>
                  {p.percent == null ? <span className="text-xs text-muted">Sem tarefas</span> : (
                    <>
                      <div className="flex-1"><Progress value={p.percent} /></div>
                      <span className="w-12 text-right font-mono text-xs">{p.percent}%</span>
                    </>
                  )}
                </li>
              ))}
            </ul>
          </Panel>
          <Panel title="Origem das métricas">
            <ul className="flex flex-col gap-1.5 text-xs text-text-2">
              {Object.entries(data.sources).map(([k, v]) => (
                <li key={k} className="flex gap-2"><Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" /><span><strong className="text-text">{k}</strong>: {v}</span></li>
              ))}
            </ul>
          </Panel>
        </>
      )}
    </div>
  );
}
