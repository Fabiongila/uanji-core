import { Archive, ArchiveRestore, Eye, FilePlus, History, Pencil, Pin, Search, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Link, useNavigate, useParams } from "react-router-dom";
import remarkGfm from "remark-gfm";
import { api } from "@/api/client";
import { useApiMutation, useNote, useNoteRevisions, useNotes, useProjects } from "@/api/hooks";
import type { Note, NoteKind } from "@/api/types";
import { Badge, Button, Checkbox, ConfirmDialog, Dialog, EmptyState, ErrorState, Input, Loading, Panel, Select, Tabs } from "@/components/ui";
import { RelationsPanel } from "@/features/RelationsPanel";
import { clearDraft, readDraft, SAVE_LABEL, useAutosave } from "@/features/useAutosave";
import { useDebounced } from "@/lib/useDebounced";
import { cn, fmtDateTime, fmtRelative, NOTE_KIND } from "@/lib/utils";
import { useQueryClient } from "@tanstack/react-query";

type Content = { title: string; content: string };

function Editor({ note }: { note: Note }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const projects = useProjects();
  const [title, setTitle] = useState(note.title);
  const [content, setContent] = useState(note.content);
  const [mode, setMode] = useState<"edit" | "preview">(note.content ? "preview" : "edit");
  const [tags, setTags] = useState(note.tags.join(", "));
  const [showRevisions, setShowRevisions] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const draft = readDraft<Content>(`note:${note.id}`);
  const [recover, setRecover] = useState(
    () => !!draft && draft.baseRevision === note.revision && (draft.value.content !== note.content || draft.value.title !== note.title),
  );
  const revisions = useNoteRevisions(note.id, showRevisions);

  const autosave = useAutosave<Content>({
    key: `note:${note.id}`,
    revision: note.revision,
    save: async (v, base) => {
      const r = await api.patch<Note>(`/api/notes/${note.id}`, { ...v, title: v.title.trim() || "Sem título", base_revision: base });
      qc.setQueryData(["notes", "detail", note.id], r);
      void qc.invalidateQueries({ queryKey: ["notes"], exact: false, refetchType: "none" });
      return r;
    },
  });

  const meta = useApiMutation((body: Partial<Note>) => api.patch<Note>(`/api/notes/${note.id}`, body), {
    invalidate: [["notes"], ["relations"]],
    onSuccess: (r) => qc.setQueryData(["notes", "detail", note.id], r),
  });
  const archive = useApiMutation((archived: boolean) => api.post(`/api/notes/${note.id}/archive`, { archived }), {
    invalidate: [["notes"]],
    success: (_, a) => (a ? "Nota arquivada." : "Nota desarquivada."),
  });
  const del = useApiMutation(() => api.del(`/api/notes/${note.id}`, { confirm: true }), {
    invalidate: [["notes"], ["relations"]],
    success: "Nota eliminada.",
    onSuccess: () => {
      clearDraft(`note:${note.id}`);
      navigate("/notes");
    },
  });
  const restore = useApiMutation((rid: string) => api.post<Note>(`/api/notes/${note.id}/revisions/${rid}/restore`), {
    invalidate: [["notes"]],
    success: "Revisão restaurada.",
    onSuccess: (r) => {
      setTitle(r.title);
      setContent(r.content);
      autosave.setRevision(r.revision);
      setShowRevisions(false);
    },
  });

  const edit = (next: Partial<Content>) => {
    const v = { title, content, ...next };
    setTitle(v.title);
    setContent(v.content);
    autosave.change(v);
  };

  const reload = async () => {
    const fresh = await api.get<Note>(`/api/notes/${note.id}`);
    qc.setQueryData(["notes", "detail", note.id], fresh);
    setTitle(fresh.title);
    setContent(fresh.content);
    autosave.setRevision(fresh.revision);
    clearDraft(`note:${note.id}`);
  };

  return (
    <div className="flex min-w-0 flex-1 flex-col gap-3">
      {recover && draft && (
        <div role="alert" className="flex flex-wrap items-center gap-2 rounded-md border border-amber/40 bg-amber/5 px-3 py-2 text-[13px] text-amber">
          Existe um rascunho local não guardado ({fmtRelative(new Date(draft.savedAt).toISOString())}).
          <Button size="sm" variant="amber" onClick={() => { edit(draft.value); setRecover(false); }}>Recuperar</Button>
          <Button size="sm" variant="ghost" onClick={() => { clearDraft(`note:${note.id}`); setRecover(false); }}>Descartar</Button>
        </div>
      )}
      {autosave.state === "conflict" && (
        <div role="alert" className="flex items-center gap-2 rounded-md border border-danger/40 bg-danger/5 px-3 py-2 text-[13px] text-danger">
          A nota foi alterada noutro local. O seu texto está guardado como rascunho local.
          <Button size="sm" variant="ghost" onClick={() => void reload()}>Carregar versão actual</Button>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Input aria-label="Título da nota" className="h-10 min-w-0 flex-1 text-base font-semibold" value={title} onChange={(e) => edit({ title: e.target.value })} />
        <span
          className={cn(
            "text-xs",
            autosave.state === "saved" ? "text-success" : autosave.state === "error" || autosave.state === "conflict" ? "text-danger" : "text-amber",
          )}
          role="status"
          title={autosave.lastError ?? undefined}
        >
          {SAVE_LABEL[autosave.state]}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Tabs value={mode} onChange={setMode} items={[
          { value: "edit", label: <span className="inline-flex items-center gap-1"><Pencil className="h-3 w-3" /> Editar</span> },
          { value: "preview", label: <span className="inline-flex items-center gap-1"><Eye className="h-3 w-3" /> Pré-visualizar</span> },
        ]} />
        <Select aria-label="Tipo" className="w-44" value={note.kind} onChange={(e) => meta.mutate({ kind: e.target.value as NoteKind })}>
          {Object.entries(NOTE_KIND).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </Select>
        <Select aria-label="Projecto" className="w-44" value={note.project_id ?? ""} onChange={(e) => meta.mutate({ project_id: e.target.value || null })}>
          <option value="">Sem projecto</option>
          {projects.data?.items.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </Select>
        <Checkbox checked={note.in_knowledge_base} onChange={(v) => meta.mutate({ in_knowledge_base: v })} label="Base de conhecimento" />
        <Button size="icon" variant={note.pinned ? "amber" : "ghost"} onClick={() => meta.mutate({ pinned: !note.pinned })} aria-label={note.pinned ? "Desafixar" : "Fixar"}>
          <Pin className="h-4 w-4" />
        </Button>
        <div className="ml-auto flex gap-1.5">
          <Button size="sm" variant="ghost" onClick={() => setShowRevisions(true)} icon={<History className="h-3.5 w-3.5" />}>Histórico</Button>
          <Button size="sm" variant="ghost" onClick={() => archive.mutate(!note.archived_at)} icon={note.archived_at ? <ArchiveRestore className="h-3.5 w-3.5" /> : <Archive className="h-3.5 w-3.5" />}>
            {note.archived_at ? "Desarquivar" : "Arquivar"}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setConfirmDelete(true)} icon={<Trash2 className="h-3.5 w-3.5 text-danger" />}>Eliminar</Button>
        </div>
      </div>
      {mode === "edit" ? (
        <textarea
          aria-label="Conteúdo (Markdown)"
          value={content}
          onChange={(e) => edit({ content: e.target.value })}
          placeholder="Escreva em Markdown…"
          spellCheck
          className="min-h-[50vh] w-full flex-1 resize-y rounded-md border border-line-strong bg-bg-2/80 p-3 font-mono text-[13px] leading-relaxed text-text focus:border-primary/70 focus:outline-none"
        />
      ) : (
        <div className="hud-panel prose-uanji min-h-[50vh] p-4 text-[13.5px] text-text-2">
          {content ? <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown> : <p className="text-muted">Nota vazia.</p>}
        </div>
      )}
      <div className="grid gap-3 md:grid-cols-2">
        <Panel title="Etiquetas">
          <Input
            aria-label="Etiquetas separadas por vírgulas"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            onBlur={() => meta.mutate({ tags: tags.split(",").map((t) => t.trim()).filter(Boolean) })}
            placeholder="python, fastapi, decisão"
          />
          {note.source_url && <a className="mt-2 block truncate text-xs text-primary" href={note.source_url} target="_blank" rel="noreferrer">{note.source_url}</a>}
        </Panel>
        <Panel title="Relações">
          <RelationsPanel type="note" id={note.id} />
        </Panel>
      </div>
      <p className="text-[11px] text-muted">Revisão {note.revision} · criada {fmtDateTime(note.created_at)} · actualizada {fmtDateTime(note.updated_at)}</p>

      <Dialog open={showRevisions} onClose={() => setShowRevisions(false)} title="Histórico de revisões" wide>
        {revisions.isLoading ? <Loading /> : (
          <ul className="flex flex-col gap-2">
            {revisions.data?.map((r) => (
              <li key={r.id} className="rounded-md border border-line p-2.5">
                <div className="flex items-center gap-2 text-xs">
                  <Badge tone="primary">Rev. {r.revision}</Badge>
                  <span className="text-muted">{fmtDateTime(r.created_at)}</span>
                  <Button size="sm" variant="ghost" className="ml-auto" loading={restore.isPending} onClick={() => restore.mutate(r.id)}>Restaurar</Button>
                </div>
                <div className="mt-1 text-[13px] text-text">{r.title}</div>
                <pre className="mt-1 max-h-24 overflow-hidden whitespace-pre-wrap font-mono text-[11px] text-muted">{r.content.slice(0, 400)}</pre>
              </li>
            ))}
          </ul>
        )}
      </Dialog>
      <ConfirmDialog open={confirmDelete} title="Eliminar nota" message={`Eliminar «${note.title}» e todo o histórico de revisões? Esta acção é irreversível.`} confirmLabel="Eliminar" loading={del.isPending} onConfirm={() => del.mutate(undefined)} onCancel={() => setConfirmDelete(false)} />
    </div>
  );
}

export default function NotesPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [kind, setKind] = useState("");
  const [archived, setArchived] = useState(false);
  const dq = useDebounced(q);
  const list = useNotes({ q: dq || undefined, kind: kind || undefined, include_archived: archived });
  const note = useNote(id);
  const create = useApiMutation(() => api.post<Note>("/api/notes", { title: "Nova nota" }), {
    invalidate: [["notes"]],
    onSuccess: (n) => navigate(`/notes/${n.id}`),
  });

  useEffect(() => {
    if (!id && list.data?.items[0] && window.innerWidth > 900) navigate(`/notes/${list.data.items[0].id}`, { replace: true });
  }, [id, list.data, navigate]);

  return (
    <div className="mx-auto flex h-full max-w-[1500px] flex-col gap-4 lg:flex-row">
      <aside className="flex w-full shrink-0 flex-col gap-2 lg:w-72">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-semibold">Notas</h1>
          <Button variant="primary" size="sm" loading={create.isPending} onClick={() => create.mutate(undefined)} icon={<FilePlus className="h-3.5 w-3.5" />}>Nova</Button>
        </div>
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted" />
          <Input aria-label="Filtrar notas" className="pl-8" placeholder="Filtrar notas" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <div className="flex gap-2">
          <Select aria-label="Tipo de nota" value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">Todos os tipos</option>
            {Object.entries(NOTE_KIND).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
        </div>
        <Checkbox checked={archived} onChange={setArchived} label="Incluir arquivadas" />
        <div className="hud-panel max-h-[40vh] overflow-y-auto lg:max-h-none lg:flex-1">
          {list.isLoading ? <div className="p-3"><Loading /></div> : list.error ? <div className="p-3"><ErrorState error={list.error} /></div> : !list.data?.items.length ? (
            <EmptyState title="Sem notas." description="Crie a primeira nota Markdown." />
          ) : (
            <ul>
              {list.data.items.map((n) => (
                <li key={n.id}>
                  <Link to={`/notes/${n.id}`} className={cn("block border-b border-line/60 px-3 py-2 hover:bg-surface-3/60", n.id === id && "bg-primary/10")}>
                    <div className="flex items-center gap-1.5">
                      {n.pinned && <Pin className="h-3 w-3 shrink-0 text-amber" />}
                      <span className="truncate text-[13px] text-text">{n.title}</span>
                    </div>
                    <div className="flex items-center gap-1.5 text-[11px] text-muted">
                      <span>{NOTE_KIND[n.kind]}</span>·<span>{fmtRelative(n.updated_at)}</span>
                      {n.archived_at && <span>· arquivada</span>}
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>
      <section className="flex min-w-0 flex-1">
        {!id ? (
          <Panel className="flex-1"><EmptyState title="Seleccione ou crie uma nota." /></Panel>
        ) : note.isLoading ? <Loading /> : note.error || !note.data ? <ErrorState error={note.error} onRetry={() => void note.refetch()} /> : (
          <Editor key={note.data.id} note={note.data} />
        )}
      </section>
    </div>
  );
}
