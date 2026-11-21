import { CheckCircle2, ChevronLeft, ChevronRight, Plus, X } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/api/client";
import { useApiMutation, useReview } from "@/api/hooks";
import type { Review, ReviewGoal, Task } from "@/api/types";
import { Badge, Button, Checkbox, EmptyState, ErrorState, Field, Input, Loading, PageHeader, Panel, Textarea } from "@/components/ui";
import { TaskRow } from "@/features/common";
import { EventDialog } from "@/pages/Agenda";
import { addDays, fmtMinutes, isoDay, startOfWeek } from "@/lib/utils";

function TaskList({ title, tasks, empty }: { title: string; tasks: Task[]; empty: string }) {
  return (
    <Panel title={`${title} (${tasks.length})`}>
      {tasks.length ? <ul>{tasks.map((t) => <TaskRow key={t.id} task={t} />)}</ul> : <p className="text-xs text-muted">{empty}</p>}
    </Panel>
  );
}

export function ReviewWorkspace({ kind }: { kind: "daily" | "weekly" }) {
  const [day, setDay] = useState(() => (kind === "weekly" ? startOfWeek(new Date()) : new Date()));
  const dayIso = isoDay(day);
  const { data, isLoading, error, refetch } = useReview(kind, dayIso);
  const [form, setForm] = useState<Omit<Review, "id" | "kind" | "period_start" | "closed_at" | "updated_at"> | null>(null);
  const [goal, setGoal] = useState("");
  const [block, setBlock] = useState(false);

  useEffect(() => {
    if (data) {
      const r = data.review;
      setForm({ goals: r.goals, wins: r.wins, blockers: r.blockers, reflection: r.reflection, next_plan: r.next_plan });
    }
  }, [data]);

  const save = useApiMutation(
    (body: Partial<Review> & { closed?: boolean }) => api.put<Review>(`/api/reviews/${kind}/${dayIso}`, body),
    { invalidate: [["reviews"]], success: (_, b) => (b.closed ? "Revisão concluída." : "Revisão guardada.") },
  );

  if (isLoading || !form) return error ? <ErrorState error={error} onRetry={() => void refetch()} /> : <Loading />;
  if (!data) return <ErrorState error={error} />;
  const closed = !!data.review.closed_at;
  const step = kind === "weekly" ? 7 : 1;
  const setGoals = (goals: ReviewGoal[]) => {
    setForm({ ...form, goals });
    save.mutate({ goals });
  };
  const label = kind === "weekly"
    ? `Semana de ${day.toLocaleDateString("pt-PT", { day: "numeric", month: "long" })} a ${addDays(day, 6).toLocaleDateString("pt-PT", { day: "numeric", month: "long" })}`
    : day.toLocaleDateString("pt-PT", { weekday: "long", day: "numeric", month: "long" });

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-4">
      <PageHeader
        title={kind === "weekly" ? "Planeamento semanal" : "Revisão diária"}
        subtitle={label}
        actions={
          <>
            <Button size="icon" variant="ghost" aria-label="Anterior" onClick={() => setDay(addDays(day, -step))}><ChevronLeft className="h-4 w-4" /></Button>
            <Button size="sm" variant="ghost" onClick={() => setDay(kind === "weekly" ? startOfWeek(new Date()) : new Date())}>{kind === "weekly" ? "Esta semana" : "Hoje"}</Button>
            <Button size="icon" variant="ghost" aria-label="Seguinte" onClick={() => setDay(addDays(day, step))}><ChevronRight className="h-4 w-4" /></Button>
            {closed ? <Badge tone="success"><CheckCircle2 className="h-3 w-3" /> Concluída</Badge> : null}
          </>
        }
      />
      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title={kind === "weekly" ? "Objectivos da semana" : "Objectivos do dia"} className="lg:col-span-1">
          <ul className="mb-2 flex flex-col gap-1.5">
            {form.goals.map((g, i) => (
              <li key={i} className="group flex items-center gap-2">
                <Checkbox checked={g.done} onChange={(done) => setGoals(form.goals.map((x, j) => (j === i ? { ...x, done } : x)))} label={<span className={g.done ? "text-muted line-through" : "text-text"}>{g.text}</span>} />
                <button type="button" className="ml-auto opacity-0 focus:opacity-100 group-hover:opacity-100" aria-label="Remover objectivo" onClick={() => setGoals(form.goals.filter((_, j) => j !== i))}><X className="h-3.5 w-3.5 text-muted" /></button>
              </li>
            ))}
            {form.goals.length === 0 && <li className="text-xs text-muted">Defina até 3 resultados concretos.</li>}
          </ul>
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); if (goal.trim()) { setGoals([...form.goals, { text: goal.trim(), done: false }]); setGoal(""); } }}>
            <Input aria-label="Novo objectivo" placeholder="Novo objectivo" value={goal} onChange={(e) => setGoal(e.target.value)} />
            <Button type="submit" size="icon" aria-label="Adicionar objectivo"><Plus className="h-4 w-4" /></Button>
          </form>
          <div className="mt-4 rounded-md border border-line px-3 py-2 text-xs text-muted">
            Foco registado no período: <span className="font-mono text-amber">{fmtMinutes(data.focus_minutes)}</span>
            <div>{data.events.length} evento(s)/bloco(s) na agenda.</div>
          </div>
          <Button className="mt-3 w-full" onClick={() => setBlock(true)}>Planear bloco de trabalho</Button>
        </Panel>
        <div className="grid gap-4 lg:col-span-2 md:grid-cols-2">
          <TaskList title="Concluídas" tasks={data.completed} empty="Nada concluído neste período." />
          <TaskList title="Adiadas" tasks={data.postponed} empty="Nenhum prazo adiado neste período." />
          <TaskList title="Atrasadas (agora)" tasks={data.overdue} empty="Sem tarefas atrasadas." />
          <TaskList title={kind === "weekly" ? "Prazos da próxima semana" : "Prazos de amanhã"} tasks={data.due_next} empty="Sem prazos." />
        </div>
      </div>
      <Panel title="Reflexão e plano">
        <div className="grid gap-3 md:grid-cols-2">
          <Field label="O que correu bem" htmlFor="r-wins"><Textarea id="r-wins" value={form.wins} onChange={(e) => setForm({ ...form, wins: e.target.value })} /></Field>
          <Field label="Bloqueios" htmlFor="r-block"><Textarea id="r-block" value={form.blockers} onChange={(e) => setForm({ ...form, blockers: e.target.value })} /></Field>
          <Field label="Reflexão" htmlFor="r-refl"><Textarea id="r-refl" value={form.reflection} onChange={(e) => setForm({ ...form, reflection: e.target.value })} /></Field>
          <Field label={kind === "weekly" ? "Plano para a próxima semana" : "Plano para amanhã"} htmlFor="r-plan"><Textarea id="r-plan" value={form.next_plan} onChange={(e) => setForm({ ...form, next_plan: e.target.value })} /></Field>
        </div>
        <div className="mt-3 flex justify-end gap-2">
          <Button loading={save.isPending} onClick={() => save.mutate({ wins: form.wins, blockers: form.blockers, reflection: form.reflection, next_plan: form.next_plan })}>Guardar</Button>
          {closed ? (
            <Button variant="ghost" onClick={() => save.mutate({ closed: false })}>Reabrir revisão</Button>
          ) : (
            <Button variant="primary" loading={save.isPending} onClick={() => save.mutate({ wins: form.wins, blockers: form.blockers, reflection: form.reflection, next_plan: form.next_plan, closed: true })}>Concluir revisão</Button>
          )}
        </div>
      </Panel>
      {data.completed.length + data.overdue.length + data.due_next.length === 0 && form.goals.length === 0 && (
        <EmptyState title="Período sem registos." description="Os dados aparecem à medida que conclui tarefas, define prazos e regista sessões de foco." />
      )}
      {block && <EventDialog open onClose={() => setBlock(false)} initial={{ start: new Date(addDays(day, kind === "weekly" ? 0 : 1).setHours(9, 0, 0, 0)), kind: "work_block" }} />}
    </div>
  );
}
