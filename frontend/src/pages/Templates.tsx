import { Copy, FolderPlus, ListPlus, Plus, Trash2, X } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "@/api/client";
import { useApiMutation, useChecklist, useChecklists, useProjects } from "@/api/hooks";
import type { Checklist } from "@/api/types";
import { Badge, Button, Checkbox, ConfirmDialog, Dialog, EmptyState, ErrorState, Field, Input, Loading, PageHeader, Panel, Progress, Select, Tabs, Textarea } from "@/components/ui";
import { FromTemplateDialog } from "@/pages/Projects";
import { cn } from "@/lib/utils";

function ChecklistView({ id }: { id: string }) {
  const { data: c, isLoading, error } = useChecklist(id);
  const projects = useProjects();
  const navigate = useNavigate();
  const [text, setText] = useState("");
  const [section, setSection] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [applyOpen, setApplyOpen] = useState(false);
  const [projectTpl, setProjectTpl] = useState(false);
  const [applyProject, setApplyProject] = useState("");
  const inv = [["checklists"]];
  const toggle = useApiMutation((v: { id: string; done: boolean }) => api.patch(`/api/checklist-items/${v.id}`, { done: v.done }), { invalidate: inv });
  const add = useApiMutation(() => api.post(`/api/checklists/${id}/items`, { text, section }), { invalidate: inv, onSuccess: () => setText("") });
  const rm = useApiMutation((iid: string) => api.del(`/api/checklist-items/${iid}`), { invalidate: inv });
  const rename = useApiMutation((body: Partial<Checklist>) => api.patch(`/api/checklists/${id}`, body), { invalidate: inv, success: "Guardado." });
  const dup = useApiMutation((as_template: boolean) => api.post<Checklist>(`/api/checklists/${id}/duplicate`, { as_template }), {
    invalidate: inv,
    success: "Duplicado.",
    onSuccess: (n) => navigate(`/templates/${n.id}`),
  });
  const apply = useApiMutation(() => api.post<Checklist>(`/api/checklists/${id}/duplicate`, { as_template: false, project_id: applyProject || null }), {
    invalidate: inv,
    success: "Checklist criada a partir do modelo.",
    onSuccess: (n) => {
      setApplyOpen(false);
      navigate(`/templates/${n.id}`);
    },
  });
  const del = useApiMutation(() => api.del(`/api/checklists/${id}`, { confirm: true }), {
    invalidate: inv,
    success: "Eliminado.",
    onSuccess: () => navigate("/templates"),
  });

  if (isLoading) return <Loading />;
  if (error || !c) return <ErrorState error={error} />;
  const sections = [...new Set(c.items.map((i) => i.section))];

  return (
    <Panel
      className="flex-1"
      title={
        <div className="flex min-w-0 items-center gap-2">
          <Badge tone={c.is_template ? "amber" : "primary"}>{c.is_template ? "Modelo" : "Checklist"}</Badge>
          {c.builtin_key && <Badge>incluído</Badge>}
        </div>
      }
      actions={
        <>
          {c.is_template && (
            <>
              <Button size="sm" variant="primary" onClick={() => setProjectTpl(true)} icon={<FolderPlus className="h-3.5 w-3.5" />}>Criar projecto</Button>
              <Button size="sm" onClick={() => setApplyOpen(true)} icon={<ListPlus className="h-3.5 w-3.5" />}>Usar como checklist</Button>
            </>
          )}
          <Button size="sm" variant="ghost" onClick={() => dup.mutate(c.is_template)} icon={<Copy className="h-3.5 w-3.5" />}>Duplicar</Button>
          {!c.is_template && <Button size="sm" variant="ghost" onClick={() => dup.mutate(true)}>Guardar como modelo</Button>}
          <Button size="sm" variant="ghost" onClick={() => setConfirmDelete(true)} aria-label="Eliminar"><Trash2 className="h-3.5 w-3.5 text-danger" /></Button>
        </>
      }
    >
      <Input key={`t-${c.updated_at}`} aria-label="Título" className="mb-2 h-9 text-base font-semibold" defaultValue={c.title} onBlur={(e) => e.target.value.trim() && e.target.value !== c.title && rename.mutate({ title: e.target.value })} />
      <Textarea key={`d-${c.updated_at}`} aria-label="Descrição" rows={2} defaultValue={c.description} onBlur={(e) => e.target.value !== c.description && rename.mutate({ description: e.target.value })} placeholder="Descrição" />
      {!c.is_template && (
        <div className="my-3 flex items-center gap-2">
          <Progress value={c.percent} tone="amber" />
          <span className="font-mono text-xs">{c.percent}%</span>
          {c.project_id && <Link to={`/projects/${c.project_id}`} className="text-xs text-primary">Ver projecto</Link>}
          {c.task_id && <Link to={`/tasks/${c.task_id}`} className="text-xs text-primary">Ver tarefa</Link>}
        </div>
      )}
      <div className="mt-3 flex flex-col gap-4">
        {sections.map((s) => (
          <div key={s || "_"}>
            <div className="hud-label mb-1.5">{s || "Geral"}</div>
            <ul className="flex flex-col gap-1">
              {c.items.filter((i) => i.section === s).map((i) => (
                <li key={i.id} className="group flex items-center gap-2">
                  {c.is_template ? (
                    <span className="text-[13px] text-text-2">• {i.text}</span>
                  ) : (
                    <Checkbox checked={i.done} onChange={(done) => toggle.mutate({ id: i.id, done })} label={<span className={cn(i.done && "text-muted line-through")}>{i.text}</span>} />
                  )}
                  <button type="button" className="ml-auto opacity-0 focus:opacity-100 group-hover:opacity-100" onClick={() => rm.mutate(i.id)} aria-label={`Remover ${i.text}`}>
                    <X className="h-3.5 w-3.5 text-muted hover:text-danger" />
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
        {c.items.length === 0 && <p className="text-xs text-muted">Sem itens.</p>}
      </div>
      <form className="mt-4 flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); if (text.trim()) add.mutate(undefined); }}>
        <Input aria-label="Novo item" placeholder="Novo item" className="min-w-48 flex-1" value={text} onChange={(e) => setText(e.target.value)} />
        <Input aria-label="Secção" placeholder="Secção" className="w-40" list="sections" value={section} onChange={(e) => setSection(e.target.value)} />
        <datalist id="sections">{sections.map((s) => <option key={s} value={s} />)}</datalist>
        <Button type="submit" loading={add.isPending} icon={<Plus className="h-3.5 w-3.5" />}>Adicionar</Button>
      </form>

      <Dialog open={applyOpen} onClose={() => setApplyOpen(false)} title="Usar modelo como checklist" footer={<><Button variant="ghost" onClick={() => setApplyOpen(false)}>Cancelar</Button><Button variant="primary" loading={apply.isPending} onClick={() => apply.mutate(undefined)}>Criar checklist</Button></>}>
        <Field label="Associar a projecto (opcional)" htmlFor="apply-p">
          <Select id="apply-p" value={applyProject} onChange={(e) => setApplyProject(e.target.value)}>
            <option value="">Nenhum</option>
            {projects.data?.items.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </Select>
        </Field>
      </Dialog>
      <FromTemplateDialog open={projectTpl} onClose={() => setProjectTpl(false)} templateId={c.id} />
      <ConfirmDialog open={confirmDelete} title="Eliminar" message={`Eliminar «${c.title}»? As checklists já criadas a partir dele não são afectadas.`} confirmLabel="Eliminar" loading={del.isPending} onConfirm={() => del.mutate(undefined)} onCancel={() => setConfirmDelete(false)} />
    </Panel>
  );
}

export default function TemplatesPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [tab, setTab] = useState<"templates" | "checklists">("templates");
  const list = useChecklists({ is_template: tab === "templates" });
  const create = useApiMutation(
    () => api.post<Checklist>("/api/checklists", { title: tab === "templates" ? "Novo modelo" : "Nova checklist", is_template: tab === "templates" }),
    { invalidate: [["checklists"]], onSuccess: (c) => navigate(`/templates/${c.id}`) },
  );
  return (
    <div className="mx-auto max-w-[1400px]">
      <PageHeader
        title="Modelos e checklists"
        subtitle="Modelos reutilizáveis (editáveis) e checklists em uso."
        actions={<Button variant="primary" onClick={() => create.mutate(undefined)} loading={create.isPending} icon={<Plus className="h-4 w-4" />}>{tab === "templates" ? "Novo modelo" : "Nova checklist"}</Button>}
      />
      <div className="flex flex-col gap-4 lg:flex-row">
        <aside className="w-full shrink-0 lg:w-80">
          <Tabs value={tab} onChange={setTab} items={[{ value: "templates", label: "Modelos" }, { value: "checklists", label: "Checklists" }]} />
          <div className="hud-panel mt-2 max-h-[70vh] overflow-y-auto">
            {list.isLoading ? <div className="p-3"><Loading /></div> : !list.data?.length ? <EmptyState title="Nada aqui ainda." /> : (
              <ul>
                {list.data.map((c) => (
                  <li key={c.id}>
                    <Link to={`/templates/${c.id}`} className={cn("block border-b border-line/60 px-3 py-2 hover:bg-surface-3/60", c.id === id && "bg-primary/10")}>
                      <div className="truncate text-[13px] text-text">{c.title}</div>
                      <div className="text-[11px] text-muted">
                        {c.category || "Geral"} · {c.items.length} itens{!c.is_template && ` · ${c.percent}%`}
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </aside>
        {id ? <ChecklistView key={id} id={id} /> : <Panel className="flex-1"><EmptyState title="Seleccione um modelo ou checklist." description="Os modelos incluídos cobrem projectos de software, APIs, revisão de código, publicação, análise de dados, datasets e revisão semanal." /></Panel>}
      </div>
    </div>
  );
}
