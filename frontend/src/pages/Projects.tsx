import { FolderPlus, LayoutTemplate, Search } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "@/api/client";
import { useApiMutation, useChecklists, useProjects } from "@/api/hooks";
import type { Priority, ProjectDetail, ProjectStatus } from "@/api/types";
import { Button, Checkbox, Dialog, EmptyState, ErrorState, Field, Input, Loading, PageHeader, Panel, Progress, Select } from "@/components/ui";
import { PriorityBadge, ProjectStatusBadge } from "@/features/common";
import { ProjectFormDialog } from "@/features/forms";
import { useDebounced } from "@/lib/useDebounced";
import { fmtDate, fmtRelative, PRIORITY, PROJECT_STATUS } from "@/lib/utils";

export function FromTemplateDialog({ open, onClose, templateId }: { open: boolean; onClose: () => void; templateId?: string }) {
  const templates = useChecklists({ is_template: true });
  const navigate = useNavigate();
  const [tpl, setTpl] = useState(templateId ?? "");
  const [name, setName] = useState("");
  const [priority, setPriority] = useState<Priority>("medium");
  const [createTasks, setCreateTasks] = useState(true);
  const create = useApiMutation(
    () => api.post<ProjectDetail>("/api/projects/from-template", { template_id: tpl || templateId, name, priority, create_tasks: createTasks }),
    {
      invalidate: [["projects"], ["tasks"], ["checklists"]],
      success: (p) => `Projecto criado a partir do modelo: ${p.name}`,
      onSuccess: (p) => {
        onClose();
        navigate(`/projects/${p.id}`);
      },
    },
  );
  const selected = templates.data?.find((t) => t.id === (tpl || templateId));
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Novo projecto a partir de um modelo"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>Cancelar</Button>
          <Button variant="primary" disabled={!name.trim() || !(tpl || templateId)} loading={create.isPending} onClick={() => create.mutate(undefined)}>
            Criar projecto
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <Field label="Modelo" htmlFor="tpl">
          <Select id="tpl" value={tpl || templateId || ""} onChange={(e) => setTpl(e.target.value)}>
            <option value="">Escolha um modelo…</option>
            {templates.data?.map((t) => (
              <option key={t.id} value={t.id}>{t.title} ({t.items.length} itens)</option>
            ))}
          </Select>
        </Field>
        {selected && <p className="text-xs text-muted">{selected.description}</p>}
        <Field label="Nome do projecto" htmlFor="tpl-name">
          <Input id="tpl-name" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
        </Field>
        <Field label="Prioridade" htmlFor="tpl-prio">
          <Select id="tpl-prio" value={priority} onChange={(e) => setPriority(e.target.value as Priority)}>
            {Object.entries(PRIORITY).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
        </Field>
        <Checkbox checked={createTasks} onChange={setCreateTasks} label="Criar uma tarefa por cada item do modelo" />
        <p className="text-xs text-muted">A checklist do modelo é copiada para o projecto. O modelo original não é alterado.</p>
      </div>
    </Dialog>
  );
}

export default function ProjectsPage() {
  const [status, setStatus] = useState<ProjectStatus | "">("");
  const [q, setQ] = useState("");
  const [archived, setArchived] = useState(false);
  const [creating, setCreating] = useState(false);
  const [fromTpl, setFromTpl] = useState(false);
  const dq = useDebounced(q);
  const { data, isLoading, error, refetch } = useProjects({ status: status || undefined, q: dq || undefined, include_archived: archived });

  return (
    <div className="mx-auto max-w-[1400px]">
      <PageHeader
        title="Projectos"
        subtitle="Progresso = tarefas de topo concluídas ÷ tarefas de topo não arquivadas."
        actions={
          <>
            <Button variant="ghost" onClick={() => setFromTpl(true)} icon={<LayoutTemplate className="h-4 w-4" />}>A partir de modelo</Button>
            <Button variant="primary" onClick={() => setCreating(true)} icon={<FolderPlus className="h-4 w-4" />}>Novo projecto</Button>
          </>
        }
      />
      <Panel bodyClassName="p-0">
        <div className="flex flex-wrap items-center gap-2 border-b border-line p-3">
          <div className="relative min-w-48 flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted" />
            <Input aria-label="Filtrar projectos" placeholder="Filtrar por nome ou descrição" className="pl-8" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <Select aria-label="Estado" className="w-40" value={status} onChange={(e) => setStatus(e.target.value as ProjectStatus | "")}>
            <option value="">Todos os estados</option>
            {Object.entries(PROJECT_STATUS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
          <Checkbox checked={archived} onChange={setArchived} label="Incluir arquivados" />
        </div>
        {isLoading ? (
          <div className="p-4"><Loading /></div>
        ) : error ? (
          <div className="p-4"><ErrorState error={error} onRetry={() => void refetch()} /></div>
        ) : !data?.items.length ? (
          <EmptyState
            title={q || status ? "Nenhum projecto corresponde aos filtros." : "Ainda não existem projectos."}
            action={!q && !status ? <Button variant="primary" onClick={() => setCreating(true)}>Criar projecto</Button> : undefined}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-[13px]">
              <thead className="text-xs text-muted">
                <tr>
                  <th className="px-3 py-2 font-medium">Nome</th>
                  <th className="px-3 py-2 font-medium">Estado</th>
                  <th className="px-3 py-2 font-medium">Prioridade</th>
                  <th className="w-44 px-3 py-2 font-medium">Progresso</th>
                  <th className="px-3 py-2 font-medium">Prazo</th>
                  <th className="px-3 py-2 text-right font-medium">Última actividade</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((p) => (
                  <tr key={p.id} className="border-t border-line/60 hover:bg-surface-3/40">
                    <td className="px-3 py-2.5">
                      <Link to={`/projects/${p.id}`} className="font-medium text-text hover:text-primary">{p.name}</Link>
                      <div className="text-xs text-muted">{p.category || "Sem categoria"}{p.stale && <span className="ml-2 text-amber">sem actividade há 14+ dias</span>}</div>
                    </td>
                    <td className="px-3 py-2.5"><ProjectStatusBadge status={p.status} /></td>
                    <td className="px-3 py-2.5"><PriorityBadge priority={p.priority} /></td>
                    <td className="px-3 py-2.5">
                      {p.progress?.percent == null ? (
                        <span className="text-xs text-muted">Sem tarefas</span>
                      ) : (
                        <div className="flex items-center gap-2">
                          <Progress value={p.progress.percent} />
                          <span className="w-16 text-right font-mono text-xs text-text-2">{p.progress.tasks_done}/{p.progress.tasks_total}</span>
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-text-2">{fmtDate(p.due_date)}</td>
                    <td className="px-3 py-2.5 text-right text-xs text-muted">{fmtRelative(p.last_activity_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="border-t border-line px-3 py-2 text-xs text-muted">{data.total} projecto(s)</div>
          </div>
        )}
      </Panel>
      <ProjectFormDialog open={creating} onClose={() => setCreating(false)} />
      <FromTemplateDialog open={fromTpl} onClose={() => setFromTpl(false)} />
    </div>
  );
}
