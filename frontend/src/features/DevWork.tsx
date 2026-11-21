import { Copy, GitBranch, GitCommit, GitPullRequest, Plus, RefreshCw, Rocket, CircleDot, Tag } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, errorMessage } from "@/api/client";
import { useApiMutation } from "@/api/hooks";
import type { TaskDetail } from "@/api/types";
import { Badge, Button, Dialog, EmptyState, Field, Input, Loading, Progress, Select, Tabs, type Tone } from "@/components/ui";
import { useGoals } from "@/features/PerformanceCenter";
import { toast } from "@/lib/toast";
import { fmtRelative } from "@/lib/utils";

type TaskTag = { id: string; ref: string; title: string; status: string };
interface RepoView {
  repo: string;
  url: string;
  error?: string;
  commits: { sha: string; message: string; author: string; date: string | null; url: string; tasks: TaskTag[] }[];
  branches: { name: string; sha: string; tasks: TaskTag[] }[];
  pulls: { number: number; title: string; state: string; branch: string; author: string; url: string; date: string | null; tasks: TaskTag[] }[];
  issues: { number: number; title: string; state: string; author: string; url: string; date: string | null; tasks: TaskTag[] }[];
  releases: { tag: string; name: string; date: string | null; url: string }[];
}
export interface Version {
  id: string;
  project_id: string;
  name: string;
  description: string;
  target_date: string | null;
  status: "planned" | "in_progress" | "released";
  released_at: string | null;
  git_tag: string;
  tasks_total: number;
  tasks_done: number;
  percent: number | null;
  code_links: number;
}
interface CodeLink {
  id: string;
  kind: "commit" | "pr" | "branch" | "issue";
  repo: string;
  ref: string;
  title: string;
  url: string;
  state: string;
  author: string;
  happened_at: string | null;
}

const STATE_TONE: Record<string, Tone> = { open: "blue", merged: "success", closed: "neutral" };
const KIND_ICON = { commit: GitCommit, pr: GitPullRequest, branch: GitBranch, issue: CircleDot };

export const useVersions = (projectId: string | null | undefined) =>
  useQuery({ queryKey: ["versions", projectId], queryFn: () => api.get<Version[]>(`/api/projects/${projectId}/versions`), enabled: !!projectId });

function TaskChips({ tasks }: { tasks: TaskTag[] }) {
  return (
    <>
      {tasks.map((t) => (
        <Link key={t.id} to={`/tasks/${t.id}`} title={t.title}>
          <Badge tone={t.status === "done" ? "success" : "primary"}>{t.ref}</Badge>
        </Link>
      ))}
    </>
  );
}

/** Repositórios do projecto (GitHub e pastas locais), com cada alteração ligada à tarefa referida (UJ-n). */
export function ProjectCode({ projectId }: { projectId: string }) {
  const [tab, setTab] = useState<"commits" | "branches" | "pulls" | "issues" | "releases">("commits");
  const code = useQuery({ queryKey: ["code", projectId], queryFn: () => api.get<{ repos: RepoView[]; ref_hint: string }>(`/api/projects/${projectId}/code`), staleTime: 60_000 });
  const sync = useApiMutation(() => api.post<{ new_links: number; repos: string[]; errors: string[] }>(`/api/projects/${projectId}/code/sync`), {
    invalidate: [["code", projectId], ["versions", projectId], ["tasks"]],
    success: (r) => `${r.new_links} ligação(ões) nova(s) entre código e tarefas${r.errors.length ? ` · ${r.errors.length} erro(s)` : ""}.`,
  });
  if (code.isLoading) return <Loading label="A ler os repositórios…" />;
  const repos = code.data?.repos ?? [];
  if (!repos.length) {
    return (
      <EmptyState
        icon={<GitBranch className="h-8 w-8" />}
        title="Sem repositórios ligados"
        description="Adicione em «Repositórios e links» um endereço GitHub ou uma pasta local com Git (tipo «Pasta local»)."
      />
    );
  }
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Tabs value={tab} onChange={setTab} items={[
          { value: "commits", label: "Commits" },
          { value: "branches", label: "Branches" },
          { value: "pulls", label: "Pull requests" },
          { value: "issues", label: "Issues" },
          { value: "releases", label: "Releases e tags" },
        ]} />
        <Button size="sm" className="ml-auto" variant="secondary" loading={sync.isPending} icon={<RefreshCw className="h-3.5 w-3.5" />} onClick={() => sync.mutate(undefined)}>
          Ligar código às tarefas
        </Button>
      </div>
      <p className="text-[11.5px] text-muted">{code.data?.ref_hint} Ex.: <code className="font-mono">git commit -m "feat: paginação UJ-41"</code> ou branch <code className="font-mono">feature/uj-41-paginacao</code>.</p>
      {repos.map((r) => (
        <section key={r.repo} aria-label={`Repositório ${r.repo}`} className="rounded-md border border-line p-3">
          <div className="mb-2 flex items-center gap-2 text-[13px]">
            <GitBranch className="h-4 w-4 text-primary" />
            {r.url.startsWith("http") ? <a href={r.url} target="_blank" rel="noreferrer" className="font-medium text-primary hover:underline">{r.repo}</a> : <span className="font-medium">{r.repo}</span>}
            {!r.url.startsWith("http") && <Badge>local</Badge>}
          </div>
          {r.error ? (
            <p className="text-[12.5px] text-danger">{r.error}</p>
          ) : (
            <ul className="flex flex-col text-[12.5px]">
              {tab === "commits" && r.commits.map((c) => (
                <li key={c.sha} className="flex flex-wrap items-center gap-2 border-b border-line/50 py-1.5 last:border-0">
                  <span className="font-mono text-[11px] text-amber">{c.sha}</span>
                  <span className="min-w-0 flex-1 truncate">{c.url ? <a href={c.url} target="_blank" rel="noreferrer" className="hover:text-primary">{c.message}</a> : c.message}</span>
                  <TaskChips tasks={c.tasks} />
                  <span className="text-[11px] text-muted">{c.author} · {fmtRelative(c.date)}</span>
                </li>
              ))}
              {tab === "branches" && r.branches.map((b) => (
                <li key={b.name} className="flex items-center gap-2 border-b border-line/50 py-1.5 last:border-0">
                  <GitBranch className="h-3.5 w-3.5 text-text-2" /><span className="font-mono">{b.name}</span><TaskChips tasks={b.tasks} />
                </li>
              ))}
              {tab === "pulls" && (r.pulls.length ? r.pulls.map((p) => (
                <li key={p.number} className="flex flex-wrap items-center gap-2 border-b border-line/50 py-1.5 last:border-0">
                  <span className="font-mono text-[11px] text-muted">#{p.number}</span>
                  <a href={p.url} target="_blank" rel="noreferrer" className="min-w-0 flex-1 truncate hover:text-primary">{p.title}</a>
                  <TaskChips tasks={p.tasks} />
                  <Badge tone={STATE_TONE[p.state] ?? "neutral"}>{p.state === "merged" ? "integrado" : p.state === "open" ? "aberto" : "fechado"}</Badge>
                </li>
              )) : <li className="text-muted">{r.url.startsWith("http") ? "Sem pull requests." : "Pull requests só existem em repositórios GitHub."}</li>)}
              {tab === "issues" && (r.issues.length ? r.issues.map((i) => (
                <li key={i.number} className="flex flex-wrap items-center gap-2 border-b border-line/50 py-1.5 last:border-0">
                  <span className="font-mono text-[11px] text-muted">#{i.number}</span>
                  <a href={i.url} target="_blank" rel="noreferrer" className="min-w-0 flex-1 truncate hover:text-primary">{i.title}</a>
                  <TaskChips tasks={i.tasks} />
                  <Badge tone={STATE_TONE[i.state] ?? "neutral"}>{i.state === "open" ? "aberta" : "fechada"}</Badge>
                </li>
              )) : <li className="text-muted">{r.url.startsWith("http") ? "Sem issues." : "Issues só existem em repositórios GitHub."}</li>)}
              {tab === "releases" && (r.releases.length ? r.releases.map((x) => (
                <li key={x.tag} className="flex items-center gap-2 border-b border-line/50 py-1.5 last:border-0">
                  <Tag className="h-3.5 w-3.5 text-amber" /><span className="font-mono">{x.tag}</span><span className="text-text-2">{x.name !== x.tag ? x.name : ""}</span>
                  <span className="ml-auto text-[11px] text-muted">{fmtRelative(x.date)}</span>
                </li>
              )) : <li className="text-muted">Sem releases ou tags.</li>)}
            </ul>
          )}
        </section>
      ))}
    </div>
  );
}

function VersionDialog({ projectId, version, onClose }: { projectId: string; version: Version | null; onClose: () => void }) {
  const [f, setF] = useState({ name: version?.name ?? "", description: version?.description ?? "", target_date: version?.target_date ?? "", status: version?.status ?? "planned", git_tag: version?.git_tag ?? "" });
  const save = useApiMutation(
    () => {
      const body = { ...f, target_date: f.target_date || null };
      return version ? api.put<Version>(`/api/projects/${projectId}/versions/${version.id}`, body) : api.post<Version>(`/api/projects/${projectId}/versions`, body);
    },
    { invalidate: [["versions", projectId]], success: "Versão guardada.", onSuccess: onClose },
  );
  return (
    <Dialog open onClose={onClose} title={version ? `Versão ${version.name}` : "Nova versão"} footer={<Button variant="primary" disabled={!f.name.trim()} loading={save.isPending} onClick={() => save.mutate(undefined)}>Guardar</Button>}>
      <div className="flex flex-col gap-3">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Nome" htmlFor="v-n"><Input id="v-n" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="v0.4" /></Field>
          <Field label="Tag Git" htmlFor="v-t" hint="Opcional, ex.: v0.4.0"><Input id="v-t" value={f.git_tag} onChange={(e) => setF({ ...f, git_tag: e.target.value })} /></Field>
          <Field label="Data prevista" htmlFor="v-d"><Input id="v-d" type="date" value={f.target_date} onChange={(e) => setF({ ...f, target_date: e.target.value })} /></Field>
          <Field label="Estado" htmlFor="v-s">
            <Select id="v-s" value={f.status} onChange={(e) => setF({ ...f, status: e.target.value as Version["status"] })}>
              <option value="planned">Planeada</option><option value="in_progress">Em curso</option><option value="released">Lançada</option>
            </Select>
          </Field>
        </div>
        <Field label="Notas da versão" htmlFor="v-desc"><Input id="v-desc" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
      </div>
    </Dialog>
  );
}

export function ProjectVersions({ projectId }: { projectId: string }) {
  const versions = useVersions(projectId);
  const [edit, setEdit] = useState<Version | null | "new">(null);
  if (versions.isLoading) return <Loading />;
  return (
    <div className="flex flex-col gap-2">
      <div className="flex justify-end"><Button size="sm" variant="primary" icon={<Plus className="h-3.5 w-3.5" />} onClick={() => setEdit("new")}>Versão</Button></div>
      {!versions.data?.length ? (
        <EmptyState icon={<Rocket className="h-8 w-8" />} title="Sem versões" description="Crie versões (ex.: v0.4) e associe-lhes tarefas para acompanhar cada lançamento e o código que o compõe." />
      ) : (
        <ul className="flex flex-col gap-2">
          {versions.data.map((v) => (
            <li key={v.id}>
              <button type="button" onClick={() => setEdit(v)} className="w-full rounded-md border border-line p-2.5 text-left hover:border-primary/40">
                <div className="flex flex-wrap items-center gap-2 text-[13px]">
                  <Rocket className="h-4 w-4 text-amber" />
                  <span className="font-semibold">{v.name}</span>
                  <Badge tone={v.status === "released" ? "success" : v.status === "in_progress" ? "blue" : "neutral"}>{v.status === "released" ? "lançada" : v.status === "in_progress" ? "em curso" : "planeada"}</Badge>
                  {v.git_tag && <span className="font-mono text-[11px] text-muted">{v.git_tag}</span>}
                  <span className="ml-auto text-xs text-muted">{v.tasks_done}/{v.tasks_total} tarefas · {v.code_links} alterações de código{v.target_date && ` · prevista ${v.target_date.split("-").reverse().join("/")}`}</span>
                </div>
                <div className="mt-1.5"><Progress value={v.percent} tone={v.status === "released" ? "success" : "primary"} /></div>
              </button>
            </li>
          ))}
        </ul>
      )}
      {edit && <VersionDialog projectId={projectId} version={edit === "new" ? null : edit} onClose={() => setEdit(null)} />}
    </div>
  );
}

/** No detalhe da tarefa: referência para o código, objectivo, versão e alterações de código ligadas. */
export function TaskDevPanel({ task }: { task: TaskDetail }) {
  const goals = useGoals();
  const versions = useVersions(task.project_id);
  const code = useQuery({ queryKey: ["code", "task", task.id], queryFn: () => api.get<{ ref: string; links: CodeLink[] }>(`/api/tasks/${task.id}/code`) });
  const update = useApiMutation((patch: Record<string, string | null>) => api.patch(`/api/tasks/${task.id}`, patch), {
    invalidate: [["tasks"], ["goals"], ["versions"], ["performance"]],
    success: "Tarefa actualizada.",
  });
  const ref = task.number != null ? `UJ-${task.number}` : "";
  return (
    <div className="flex flex-col gap-3 text-[13px]">
      {ref && (
        <div className="flex items-center gap-2">
          <span className="hud-label">Referência</span>
          <code className="rounded bg-surface-3 px-1.5 py-0.5 font-mono text-primary">{ref}</code>
          <Button size="icon" variant="ghost" aria-label="Copiar referência" onClick={() => void navigator.clipboard?.writeText(ref).then(() => toast.success(`${ref} copiado. Use-o no commit, branch ou PR.`), (e: unknown) => toast.error(errorMessage(e)))}>
            <Copy className="h-3.5 w-3.5" />
          </Button>
        </div>
      )}
      <Field label="Objectivo" htmlFor="t-goal">
        <Select id="t-goal" value={task.goal_id ?? ""} onChange={(e) => update.mutate({ goal_id: e.target.value || null })}>
          <option value="">Nenhum</option>
          {goals.data?.map((g) => <option key={g.id} value={g.id}>{g.title}</option>)}
        </Select>
      </Field>
      {task.project_id && (
        <Field label="Versão" htmlFor="t-ver">
          <Select id="t-ver" value={task.version_id ?? ""} onChange={(e) => update.mutate({ version_id: e.target.value || null })}>
            <option value="">Nenhuma</option>
            {versions.data?.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
          </Select>
        </Field>
      )}
      <div>
        <div className="hud-label mb-1">Código ligado</div>
        {code.data?.links.length ? (
          <ul className="flex flex-col gap-1">
            {code.data.links.map((l) => {
              const Icon = KIND_ICON[l.kind];
              return (
                <li key={l.id} className="flex items-center gap-1.5 text-[12.5px]">
                  <Icon className="h-3.5 w-3.5 shrink-0 text-text-2" />
                  <span className="font-mono text-[11px] text-muted">{l.kind === "pr" || l.kind === "issue" ? `#${l.ref}` : l.kind === "commit" ? l.ref : ""}</span>
                  {l.url ? <a href={l.url} target="_blank" rel="noreferrer" className="min-w-0 truncate hover:text-primary">{l.title}</a> : <span className="min-w-0 truncate">{l.title}</span>}
                  {l.state && <Badge tone={STATE_TONE[l.state] ?? "neutral"}>{l.state}</Badge>}
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="text-[12px] text-muted">Nenhum commit, branch ou PR referencia {ref || "esta tarefa"} ainda. No projecto, use «Ligar código às tarefas».</p>
        )}
      </div>
    </div>
  );
}
