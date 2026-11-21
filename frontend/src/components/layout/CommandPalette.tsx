import { Command } from "cmdk";
import { Bot, FileCode2, FilePlus, FolderPlus, ListPlus, Loader2, Play, Search, Square, Timer, Workflow } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/api/client";
import { useQuery } from "@tanstack/react-query";
import { useApiMutation, useAutomations, useSearch } from "@/api/hooks";
import type { AutomationRun, CommandResult } from "@/api/types";
import { sendMessage } from "@/lib/voice";
import { toast } from "@/lib/toast";
import { ENTITY_LABEL } from "@/lib/utils";
import { useDebounced } from "@/lib/useDebounced";
import { NAV } from "./AppShell";

const itemCls =
  "flex h-9 cursor-pointer items-center gap-2.5 rounded-md px-2.5 text-[13px] text-text-2 data-[selected=true]:bg-primary/12 data-[selected=true]:text-text [&_svg]:h-4 [&_svg]:w-4";

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [q, setQ] = useState("");
  const dq = useDebounced(q, 180);
  const search = useSearch(dq);
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);

  const files = useQuery({
    queryKey: ["palette", "files", dq],
    queryFn: () => api.get<{ files: { path: string; relative: string; root: string }[]; hint?: string }>("/api/palette/files", { q: dq.trim(), limit: 8 }),
    enabled: open && dq.trim().length >= 2,
    staleTime: 30_000,
  });
  const automations = useAutomations();
  const openFile = useApiMutation((path: string) => api.post<{ opened: string; with: string }>("/api/palette/open-file", { path }), {
    success: (r) => `A abrir no ${r.with}.`,
    onSuccess: () => onClose(),
  });
  const runFlow = useApiMutation((id: string) => api.post<AutomationRun>(`/api/automations/${id}/run`), {
    invalidate: [["automations"], ["runs"], ["tasks"]],
    success: (r) => (r.status === "failed" ? null : `Fluxo executado (${r.status}).`),
    onSuccess: (r) => {
      onClose();
      if (r.status === "failed") toast.error(`O fluxo falhou: ${r.error}`);
    },
  });
  const ask = async (t: string) => {
    onClose();
    try {
      const turn = await sendMessage(t, false);
      toast.info(turn.reply.slice(0, 220));
      if (turn.navigate) navigate(turn.navigate);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Falha ao contactar o assistente.");
    }
  };
  const COMMANDS = [
    { id: "focus-start", label: "Iniciar sessão de foco", icon: <Timer />, run: () => quick.mutate("foco iniciar") },
    { id: "focus-stop", label: "Terminar sessão de foco", icon: <Square />, run: () => quick.mutate("foco parar") },
    { id: "daily", label: "Relatório do dia (assistente)", icon: <Bot />, run: () => void ask("faz o relatório do meu dia") },
    { id: "next", label: "O que devo fazer a seguir?", icon: <Bot />, run: () => void ask("diz-me o que devo fazer a seguir") },
    { id: "new-flow", label: "Nova automação", icon: <Workflow />, run: () => go("/automations/new") },
  ];

  const quick = useApiMutation((text: string) => api.post<CommandResult>("/api/commands", { text }), {
    invalidate: [["tasks"], ["projects"], ["notes"]],
    success: (r) => r.message,
    onSuccess: (r) => {
      onClose();
      if (r.route) navigate(r.route);
    },
  });

  useEffect(() => {
    if (open) {
      setQ("");
      window.setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [open]);

  if (!open) return null;
  const go = (to: string) => {
    onClose();
    navigate(to);
  };
  const text = q.trim();

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-bg/70 pt-[12vh] backdrop-blur-sm" onMouseDown={onClose}>
      <div className="hud-panel w-[min(640px,calc(100%-2rem))] overflow-hidden" onMouseDown={(e) => e.stopPropagation()}>
        <Command
          label="Pesquisa global"
          shouldFilter={false}
          onKeyDown={(e) => {
            if (e.key === "Escape") onClose();
          }}
        >
          <div className="flex items-center gap-2 border-b border-line px-3">
            {search.isFetching ? (
              <Loader2 className="h-4 w-4 animate-spin text-primary" />
            ) : (
              <Search className="h-4 w-4 text-muted" />
            )}
            <Command.Input
              ref={inputRef}
              value={q}
              onValueChange={setQ}
              placeholder="Pesquisar ou escrever uma acção…"
              className="h-12 flex-1 bg-transparent text-sm text-text placeholder:text-muted focus:outline-none"
            />
          </div>
          <Command.List className="max-h-[52vh] overflow-auto p-1.5">
            <Command.Empty className="px-3 py-6 text-center text-[13px] text-muted">
              {dq && search.isSuccess ? "Sem resultados." : "Escreva para pesquisar."}
            </Command.Empty>
            {text && (
              <Command.Group heading="Criar" className="[&_[cmdk-group-heading]]:hud-label [&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:py-1.5">
                <Command.Item className={itemCls} value="create-task" onSelect={() => quick.mutate(`tarefa ${text}`)}>
                  <ListPlus /> Criar tarefa «{text}»
                </Command.Item>
                <Command.Item className={itemCls} value="create-project" onSelect={() => quick.mutate(`projecto ${text}`)}>
                  <FolderPlus /> Criar projecto «{text}»
                </Command.Item>
                <Command.Item className={itemCls} value="create-note" onSelect={() => quick.mutate(`nota ${text}`)}>
                  <FilePlus /> Criar nota «{text}»
                </Command.Item>
              </Command.Group>
            )}
            {text && (
              <Command.Group heading="Assistente" className="[&_[cmdk-group-heading]]:hud-label [&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:py-1.5">
                <Command.Item className={itemCls} value="ask" onSelect={() => void ask(text)}>
                  <Bot /> Pedir ao UANJI: «{text}»
                </Command.Item>
              </Command.Group>
            )}
            {(automations.data ?? []).filter((a) => !text || a.name.toLowerCase().includes(text.toLowerCase())).length > 0 && (
              <Command.Group heading="Executar fluxo" className="[&_[cmdk-group-heading]]:hud-label [&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:py-1.5">
                {(automations.data ?? []).filter((a) => !text || a.name.toLowerCase().includes(text.toLowerCase())).slice(0, 5).map((a) => (
                  <Command.Item key={a.id} value={`flow:${a.id}`} className={itemCls} onSelect={() => runFlow.mutate(a.id)}>
                    <Play /> <span className="flex-1 truncate">Executar «{a.name}»</span>
                    {!a.enabled && <span className="text-[11px] text-muted">inactiva</span>}
                  </Command.Item>
                ))}
              </Command.Group>
            )}
            {files.data && files.data.files.length > 0 && (
              <Command.Group heading="Abrir ficheiro" className="[&_[cmdk-group-heading]]:hud-label [&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:py-1.5">
                {files.data.files.map((f) => (
                  <Command.Item key={f.path} value={`file:${f.path}`} className={itemCls} onSelect={() => openFile.mutate(f.path)}>
                    <FileCode2 />
                    <span className="min-w-0 flex-1 truncate font-mono text-[12px]">{f.relative}</span>
                    <span className="text-[11px] text-muted">{f.root}</span>
                  </Command.Item>
                ))}
              </Command.Group>
            )}
            {search.data && search.data.hits.length > 0 && (
              <Command.Group heading={`Resultados (${search.data.engine === "fts5" ? "FTS5" : "texto"})`} className="[&_[cmdk-group-heading]]:hud-label [&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:py-1.5">
                {search.data.hits.map((h) => (
                  <Command.Item key={`${h.entity_type}:${h.entity_id}`} value={`${h.entity_type}:${h.entity_id}`} className={itemCls} onSelect={() => go(h.route)}>
                    <span className="w-20 shrink-0 text-[11px] uppercase tracking-wide text-primary/80">
                      {ENTITY_LABEL[h.entity_type] ?? h.entity_type}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-text">{h.title}</span>
                      {h.snippet && <span className="block truncate text-xs text-muted">{h.snippet}</span>}
                    </span>
                  </Command.Item>
                ))}
              </Command.Group>
            )}
            <Command.Group heading="Comandos" className="[&_[cmdk-group-heading]]:hud-label [&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:py-1.5">
              {COMMANDS.filter((c) => !text || c.label.toLowerCase().includes(text.toLowerCase())).map((c) => (
                <Command.Item key={c.id} value={`cmd:${c.id}`} className={itemCls} onSelect={c.run}>
                  {c.icon} {c.label}
                </Command.Item>
              ))}
            </Command.Group>
            <Command.Group heading="Navegar" className="[&_[cmdk-group-heading]]:hud-label [&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:py-1.5">
              {NAV.filter((n) => !text || n.label.toLowerCase().includes(text.toLowerCase())).map((n) => (
                <Command.Item key={n.to} value={`nav:${n.to}`} className={itemCls} onSelect={() => go(n.to)}>
                  {n.icon} {n.label}
                </Command.Item>
              ))}
            </Command.Group>
          </Command.List>
          <div className="flex flex-wrap gap-3 border-t border-line px-3 py-1.5 font-mono text-[10.5px] text-muted">
            <span>↑↓ navegar</span><span>⏎ executar</span><span>esc fechar</span>
            <span className="ml-auto">tarefa Título !alta @amanhã</span>
          </div>
        </Command>
      </div>
    </div>
  );
}
