import { ChevronLeft, ChevronRight, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { useAgenda, useApiMutation, useProjects } from "@/api/hooks";
import type { EventItem, Task } from "@/api/types";
import { Button, ConfirmDialog, Dialog, ErrorState, Field, Input, Loading, PageHeader, Select, Tabs, Textarea } from "@/components/ui";
import { StatusIcon } from "@/features/common";
import { addDays, cn, fmtTime, isoDay, isoToLocalInput, localInputToIso, startOfWeek } from "@/lib/utils";

export function EventDialog({ open, onClose, initial, event }: { open: boolean; onClose: () => void; initial?: { start: Date; kind?: "event" | "work_block" }; event?: EventItem }) {
  const projects = useProjects();
  const start0 = event ? new Date(event.start_at) : initial?.start ?? new Date();
  const [form, setForm] = useState({
    title: event?.title ?? "",
    kind: event?.kind ?? initial?.kind ?? "event",
    start: isoToLocalInput(start0.toISOString()),
    end: isoToLocalInput((event ? new Date(event.end_at) : new Date(start0.getTime() + 60 * 60_000)).toISOString()),
    description: event?.description ?? "",
    location: event?.location ?? "",
    project_id: event?.project_id ?? "",
  });
  const [err, setErr] = useState<string | null>(null);
  const save = useApiMutation(
    () => {
      const body = {
        title: form.title, kind: form.kind, description: form.description, location: form.location,
        start_at: localInputToIso(form.start), end_at: localInputToIso(form.end), project_id: form.project_id || null,
      };
      return event ? api.patch(`/api/events/${event.id}`, body) : api.post("/api/events", body);
    },
    { invalidate: [["agenda"], ["reviews"]], success: event ? "Evento actualizado." : "Evento criado.", onSuccess: onClose },
  );
  const submit = () => {
    if (!form.title.trim()) return setErr("Indique o título.");
    if (!form.start || !form.end || new Date(form.end) <= new Date(form.start)) return setErr("O fim tem de ser posterior ao início.");
    setErr(null);
    save.mutate(undefined);
  };
  return (
    <Dialog open={open} onClose={onClose} title={event ? "Editar evento" : "Novo evento"} footer={<><Button variant="ghost" onClick={onClose}>Cancelar</Button><Button variant="primary" loading={save.isPending} onClick={submit}>Guardar</Button></>}>
      <div className="grid gap-3">
        {err && <p role="alert" className="text-xs text-danger">{err}</p>}
        <Field label="Título" htmlFor="ev-t"><Input id="ev-t" autoFocus value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></Field>
        <Field label="Tipo" htmlFor="ev-k">
          <Select id="ev-k" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as "event" | "work_block" })}>
            <option value="event">Evento / compromisso</option>
            <option value="work_block">Bloco de trabalho</option>
          </Select>
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Início" htmlFor="ev-s"><Input id="ev-s" type="datetime-local" value={form.start} onChange={(e) => setForm({ ...form, start: e.target.value })} /></Field>
          <Field label="Fim" htmlFor="ev-e"><Input id="ev-e" type="datetime-local" value={form.end} onChange={(e) => setForm({ ...form, end: e.target.value })} /></Field>
        </div>
        <Field label="Projecto" htmlFor="ev-p">
          <Select id="ev-p" value={form.project_id} onChange={(e) => setForm({ ...form, project_id: e.target.value })}>
            <option value="">Nenhum</option>
            {projects.data?.items.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </Select>
        </Field>
        <Field label="Local" htmlFor="ev-l"><Input id="ev-l" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} /></Field>
        <Field label="Notas" htmlFor="ev-d"><Textarea id="ev-d" rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
        <p className="text-[11px] text-muted">Agenda local. Não sincroniza com calendários externos.</p>
      </div>
    </Dialog>
  );
}

function DayColumn({ day, events, tasks, onEdit, today }: { day: Date; events: EventItem[]; tasks: Task[]; onEdit: (e: EventItem) => void; today: boolean }) {
  return (
    <div className={cn("hud-panel flex min-h-48 flex-col", today && "border-primary/50")}>
      <div className="border-b border-line px-2.5 py-1.5">
        <div className={cn("hud-label", today && "text-primary")}>{day.toLocaleDateString("pt-PT", { weekday: "short" })}</div>
        <div className="font-mono text-sm text-text">{day.toLocaleDateString("pt-PT", { day: "2-digit", month: "short" })}</div>
      </div>
      <ul className="flex flex-1 flex-col gap-1.5 p-2">
        {events.map((e) => (
          <li key={e.id}>
            <button type="button" onClick={() => onEdit(e)} className={cn("w-full rounded border px-2 py-1 text-left text-xs", e.kind === "work_block" ? "border-amber/40 bg-amber/5" : "border-electric/40 bg-electric/5")}>
              <div className="font-mono text-[10.5px] text-muted">{fmtTime(e.start_at)}–{fmtTime(e.end_at)}</div>
              <div className="truncate text-text">{e.title}</div>
            </button>
          </li>
        ))}
        {tasks.map((t) => (
          <li key={t.id}>
            <Link to={`/tasks/${t.id}`} className="flex items-center gap-1.5 rounded border border-line px-2 py-1 text-xs hover:border-line-strong">
              <StatusIcon status={t.status} className="h-3.5 w-3.5" />
              <span className={cn("truncate", t.status === "done" ? "text-muted line-through" : t.overdue ? "text-danger" : "text-text-2")}>{t.title}</span>
            </Link>
          </li>
        ))}
        {events.length + tasks.length === 0 && <li className="py-3 text-center text-[11px] text-muted">Livre</li>}
      </ul>
    </div>
  );
}

export default function AgendaPage() {
  const [view, setView] = useState<"week" | "day">("week");
  const [anchor, setAnchor] = useState(() => new Date());
  const [creating, setCreating] = useState<{ start: Date; kind?: "event" | "work_block" } | null>(null);
  const [editing, setEditing] = useState<EventItem | null>(null);
  const [deleting, setDeleting] = useState<EventItem | null>(null);
  const start = view === "week" ? startOfWeek(anchor) : new Date(anchor.getFullYear(), anchor.getMonth(), anchor.getDate());
  const days = view === "week" ? 7 : 1;
  const { data, isLoading, error, refetch } = useAgenda(isoDay(start), days);
  const del = useApiMutation((id: string) => api.del(`/api/events/${id}`, { confirm: true }), { invalidate: [["agenda"]], success: "Evento eliminado.", onSuccess: () => setDeleting(null) });
  const todayIso = isoDay(new Date());
  const dayList = Array.from({ length: days }, (_, i) => addDays(start, i));
  const byDay = (d: Date) => {
    const k = isoDay(d);
    return {
      events: (data?.events ?? []).filter((e) => isoDay(new Date(e.start_at)) === k),
      tasks: (data?.tasks ?? []).filter((t) => t.due_at && isoDay(new Date(t.due_at)) === k),
    };
  };
  const nine = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate(), 9, 0);

  return (
    <div className="mx-auto max-w-[1500px]">
      <PageHeader
        title="Agenda"
        subtitle={`${start.toLocaleDateString("pt-PT", { day: "numeric", month: "long" })}${days > 1 ? ` — ${addDays(start, 6).toLocaleDateString("pt-PT", { day: "numeric", month: "long", year: "numeric" })}` : ""} · fuso ${Intl.DateTimeFormat().resolvedOptions().timeZone}`}
        actions={
          <>
            <Tabs value={view} onChange={setView} items={[{ value: "day", label: "Dia" }, { value: "week", label: "Semana" }]} />
            <Button size="icon" variant="ghost" aria-label="Anterior" onClick={() => setAnchor(addDays(anchor, -days))}><ChevronLeft className="h-4 w-4" /></Button>
            <Button size="sm" variant="ghost" onClick={() => setAnchor(new Date())}>Hoje</Button>
            <Button size="icon" variant="ghost" aria-label="Seguinte" onClick={() => setAnchor(addDays(anchor, days))}><ChevronRight className="h-4 w-4" /></Button>
            <Button onClick={() => setCreating({ start: nine(anchor), kind: "work_block" })}>Bloco de trabalho</Button>
            <Button variant="primary" onClick={() => setCreating({ start: nine(anchor) })} icon={<Plus className="h-4 w-4" />}>Evento</Button>
          </>
        }
      />
      {isLoading ? <Loading /> : error ? <ErrorState error={error} onRetry={() => void refetch()} /> : view === "week" ? (
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
          {dayList.map((d) => <DayColumn key={d.toISOString()} day={d} {...byDay(d)} onEdit={setEditing} today={isoDay(d) === todayIso} />)}
        </div>
      ) : (
        <div className="hud-panel">
          {(() => {
            const { events, tasks } = byDay(start);
            return (
              <ul className="divide-y divide-line/60">
                {events.map((e) => (
                  <li key={e.id} className="flex items-center gap-3 px-4 py-2.5">
                    <span className="w-28 font-mono text-xs text-muted">{fmtTime(e.start_at)}–{fmtTime(e.end_at)}</span>
                    <button type="button" className="flex-1 text-left text-[13px] text-text hover:text-primary" onClick={() => setEditing(e)}>{e.title}</button>
                    <span className="text-xs text-muted">{e.kind === "work_block" ? "Bloco de trabalho" : "Evento"}</span>
                    <Button size="icon" variant="ghost" aria-label="Eliminar evento" onClick={() => setDeleting(e)}><Trash2 className="h-3.5 w-3.5" /></Button>
                  </li>
                ))}
                {tasks.map((t) => (
                  <li key={t.id} className="flex items-center gap-3 px-4 py-2.5">
                    <span className="w-28 font-mono text-xs text-muted">prazo {t.due_at ? fmtTime(t.due_at) : ""}</span>
                    <Link to={`/tasks/${t.id}`} className="flex-1 text-[13px] text-text-2 hover:text-primary">{t.title}</Link>
                  </li>
                ))}
                {events.length + tasks.length === 0 && <li className="px-4 py-10 text-center text-[13px] text-muted">Dia sem eventos nem prazos.</li>}
              </ul>
            );
          })()}
        </div>
      )}
      {creating && <EventDialog open onClose={() => setCreating(null)} initial={creating} />}
      {editing && <EventDialog key={editing.id} open onClose={() => setEditing(null)} event={editing} />}
      <ConfirmDialog open={!!deleting} title="Eliminar evento" message={`Eliminar «${deleting?.title}»?`} confirmLabel="Eliminar" loading={del.isPending} onConfirm={() => deleting && del.mutate(deleting.id)} onCancel={() => setDeleting(null)} />
    </div>
  );
}
