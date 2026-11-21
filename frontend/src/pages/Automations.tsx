import { Play, Plus, Workflow } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "@/api/client";
import { useApiMutation, useAutomations } from "@/api/hooks";
import type { AutomationRun } from "@/api/types";
import { Badge, Button, EmptyState, ErrorState, Loading, PageHeader, Panel, type Tone } from "@/components/ui";
import { useCore } from "@/lib/core-state";
import { fmtDateTime, fmtRelative } from "@/lib/utils";

export const TRIGGER_LABEL: Record<string, string> = {
  manual: "Manual",
  schedule: "Programada",
  task_completed: "Tarefa concluída",
  deadline_approaching: "Prazo próximo",
  webhook: "Webhook (aplicação externa)",
  github: "Evento do GitHub",
  app_opened: "Abrir uma aplicação no Mac",
};

export const RUN_TONE: Record<string, Tone> = {
  success: "success",
  failed: "danger",
  running: "blue",
  pending: "neutral",
  cancelled: "amber",
  skipped: "neutral",
};
export const RUN_LABEL: Record<string, string> = {
  success: "Sucesso",
  failed: "Falhou",
  running: "Em execução",
  pending: "Pendente",
  cancelled: "Cancelada",
  skipped: "Ignorada",
};

export function useRunAutomation(onDone?: (r: AutomationRun) => void) {
  const { beginExecute, endExecute } = useCore();
  return useApiMutation(
    async (id: string) => {
      beginExecute();
      try {
        return await api.post<AutomationRun>(`/api/automations/${id}/run`);
      } finally {
        endExecute();
      }
    },
    {
      invalidate: [["automations"], ["tasks"], ["notes"], ["projects"]],
      success: (r) => `Execução: ${RUN_LABEL[r.status] ?? r.status}${r.error ? ` — ${r.error}` : ""}`,
      onSuccess: onDone,
    },
  );
}

export default function AutomationsPage() {
  const { data, isLoading, error, refetch } = useAutomations();
  const navigate = useNavigate();
  const run = useRunAutomation();
  return (
    <div className="mx-auto max-w-[1400px]">
      <PageHeader
        title="Automações"
        subtitle="Fluxos internos validados: gatilhos locais e acções seguras (sem shell nem código arbitrário)."
        actions={<Button variant="primary" onClick={() => navigate("/automations/new")} icon={<Plus className="h-4 w-4" />}>Nova automação</Button>}
      />
      <Panel bodyClassName="p-0">
        {isLoading ? <div className="p-4"><Loading /></div> : error ? <div className="p-4"><ErrorState error={error} onRetry={() => void refetch()} /></div> : !data?.length ? (
          <EmptyState icon={<Workflow className="h-8 w-8" />} title="Sem automações." description="Exemplo: quando uma tarefa de um projecto é concluída, criar uma nota de registo e mostrar uma notificação." action={<Button variant="primary" onClick={() => navigate("/automations/new")}>Criar automação</Button>} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] text-left text-[13px]">
              <thead className="text-xs text-muted">
                <tr>
                  <th className="px-3 py-2 font-medium">Nome</th>
                  <th className="px-3 py-2 font-medium">Gatilho</th>
                  <th className="px-3 py-2 font-medium">Estado</th>
                  <th className="px-3 py-2 font-medium">Versão</th>
                  <th className="px-3 py-2 font-medium">Última execução</th>
                  <th className="px-3 py-2 font-medium">Próxima</th>
                  <th className="px-3 py-2 font-medium">Execuções</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {data.map((a) => (
                  <tr key={a.id} className="border-t border-line/60 hover:bg-surface-3/40">
                    <td className="px-3 py-2.5">
                      <Link to={`/automations/${a.id}`} className="font-medium text-text hover:text-primary">{a.name}</Link>
                      <div className="text-xs text-muted">{a.definition.steps.length} etapa(s)</div>
                    </td>
                    <td className="px-3 py-2.5 text-text-2">{TRIGGER_LABEL[a.trigger_type]}</td>
                    <td className="px-3 py-2.5">{a.enabled ? <Badge tone="success">Activa</Badge> : <Badge>Inactiva</Badge>}</td>
                    <td className="px-3 py-2.5 font-mono text-xs">v{a.version}</td>
                    <td className="px-3 py-2.5 text-xs">
                      {a.last_run ? (
                        <span className="flex items-center gap-1.5">
                          <Badge tone={RUN_TONE[a.last_run.status]}>{RUN_LABEL[a.last_run.status]}</Badge>
                          <span className="text-muted">{fmtRelative(a.last_run.started_at)}</span>
                        </span>
                      ) : <span className="text-muted">Nunca</span>}
                    </td>
                    <td className="px-3 py-2.5 text-xs text-muted">{a.next_run_at ? fmtDateTime(a.next_run_at) : "—"}</td>
                    <td className="px-3 py-2.5 font-mono text-xs text-muted">
                      {a.run_counts.success ?? 0}✓ {a.run_counts.failed ?? 0}✗
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      <Button size="sm" loading={run.isPending && run.variables === a.id} onClick={() => run.mutate(a.id)} icon={<Play className="h-3.5 w-3.5" />}>Executar</Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}
