import { Archive, Download, FileUp, FlaskConical, RotateCcw, ShieldCheck } from "lucide-react";
import { useRef, useState } from "react";
import { api, errorMessage, request } from "@/api/client";
import { useApiMutation, useBackups } from "@/api/hooks";
import type { BackupItem } from "@/api/types";
import { Badge, Button, ConfirmDialog, EmptyState, ErrorState, Loading, PageHeader, Panel } from "@/components/ui";
import { toast } from "@/lib/toast";
import { fmtBytes, fmtDateTime } from "@/lib/utils";

const KIND: Record<string, string> = { manual: "Manual", automatic: "Automático", pre_restore: "Antes de restauro", pre_migration: "Antes de migração" };
type Counts = Record<string, number>;

async function download(path: string, filename: string) {
  const res = await request<Response>(path, { raw: true });
  if (!res.ok) throw new Error(`Falha ao descarregar (${res.status}).`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function BackupsPage() {
  const { data, isLoading, error, refetch } = useBackups();
  const [restoring, setRestoring] = useState<BackupItem | null>(null);
  const [imported, setImported] = useState<{ file: File; counts: Counts } | null>(null);
  const [info, setInfo] = useState<Record<string, string>>({});
  const fileRef = useRef<HTMLInputElement>(null);
  const create = useApiMutation(() => api.post<{ filename: string }>("/api/backups"), { invalidate: [["backups"]], success: (b) => `Backup criado: ${b.filename}` });
  const verify = useApiMutation((f: string) => api.post<{ counts: Counts }>(`/api/backups/${f}/verify`), {
    invalidate: [["backups"]],
    success: "Integridade verificada: OK.",
    onSuccess: (r, f) => setInfo((i) => ({ ...i, [f]: `Integridade OK · ${r.counts.projects} projectos, ${r.counts.tasks} tarefas, ${r.counts.notes} notas` })),
  });
  const test = useApiMutation((f: string) => api.post<{ counts: Counts }>(`/api/backups/${f}/test-restore`), {
    success: "Restauro de teste concluído numa base temporária.",
    onSuccess: (r, f) => setInfo((i) => ({ ...i, [f]: `Teste de restauro OK · ${r.counts.projects} projectos, ${r.counts.tasks} tarefas, ${r.counts.notes} notas` })),
  });
  const restore = useApiMutation((f: string) => api.post<{ safety_backup: string }>(`/api/backups/${f}/restore`, { confirm: true }), {
    invalidate: [["backups"], ["projects"], ["tasks"], ["notes"], ["checklists"], ["automations"], ["agenda"], ["vault"]],
    success: (r) => `Dados restaurados. Backup de segurança: ${r.safety_backup}`,
    onSuccess: () => setRestoring(null),
  });

  const upload = async (file: File, confirm: boolean) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<{ counts: Counts; safety_backup?: string }>("/api/backups/import", { method: "POST", body: fd, query: { confirm } });
  };
  const onFile = async (file: File) => {
    try {
      const r = await upload(file, false);
      setImported({ file, counts: r.counts });
    } catch (e) {
      toast.error(errorMessage(e));
    }
  };
  const importConfirm = useApiMutation(() => upload(imported!.file, true), {
    invalidate: [["backups"], ["projects"], ["tasks"], ["notes"], ["checklists"], ["automations"]],
    success: (r) => `Dados importados. Backup de segurança: ${r.safety_backup ?? "—"}`,
    onSuccess: () => setImported(null),
  });

  return (
    <div className="mx-auto flex max-w-[1200px] flex-col gap-4">
      <PageHeader
        title="Backups e recuperação"
        subtitle={data ? `Pasta: ${data.directory}` : undefined}
        actions={
          <>
            <input ref={fileRef} type="file" accept=".zip,application/zip" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) void onFile(f); e.target.value = ""; }} />
            <Button onClick={() => fileRef.current?.click()} icon={<FileUp className="h-4 w-4" />}>Importar backup</Button>
            <Button onClick={() => download("/api/export", "uanji-export.json").catch((e) => toast.error(errorMessage(e)))} icon={<Download className="h-4 w-4" />}>Exportar JSON</Button>
            <Button variant="primary" loading={create.isPending} onClick={() => create.mutate(undefined)} icon={<Archive className="h-4 w-4" />}>Criar backup</Button>
          </>
        }
      />
      <Panel>
        <ul className="grid gap-2 text-xs text-text-2 md:grid-cols-2">
          <li>• Cada backup é um ZIP com uma cópia consistente da base de dados e um manifesto com SHA-256.</li>
          <li>• Antes de cada restauro é criado automaticamente um backup de segurança dos dados actuais.</li>
          <li>• Os segredos do Keychain <strong>não</strong> são incluídos; num computador novo terá de os voltar a introduzir.</li>
          <li>• Automáticos: {data?.automatic.automatic ? `a cada ${data.automatic.interval_hours} h, mantendo ${data.automatic.keep}` : "desactivados"} (Definições).</li>
        </ul>
      </Panel>
      <Panel bodyClassName="p-0">
        {isLoading ? <div className="p-4"><Loading /></div> : error ? <div className="p-4"><ErrorState error={error} onRetry={() => void refetch()} /></div> : !data?.items.length ? (
          <EmptyState title="Ainda não existem backups." action={<Button variant="primary" onClick={() => create.mutate(undefined)}>Criar o primeiro backup</Button>} />
        ) : (
          <ul>
            {data.items.map((b) => (
              <li key={b.id} className="border-t border-line/60 px-3 py-2.5 first:border-0">
                <div className="flex flex-wrap items-center gap-2 text-[13px]">
                  <span className="font-mono text-xs text-text">{b.filename}</span>
                  <Badge>{KIND[b.kind] ?? b.kind}</Badge>
                  <Badge tone={b.status === "ok" ? "success" : "danger"}>{b.status === "ok" ? "Íntegro" : b.status === "missing" ? "Ficheiro em falta" : "Falhou"}</Badge>
                  <span className="text-xs text-muted">{fmtDateTime(b.created_at)} · {fmtBytes(b.size_bytes)}</span>
                  <div className="ml-auto flex gap-1">
                    <Button size="sm" variant="ghost" disabled={b.status === "missing"} loading={verify.isPending && verify.variables === b.filename} onClick={() => verify.mutate(b.filename)} icon={<ShieldCheck className="h-3.5 w-3.5" />}>Verificar</Button>
                    <Button size="sm" variant="ghost" disabled={b.status === "missing"} loading={test.isPending && test.variables === b.filename} onClick={() => test.mutate(b.filename)} icon={<FlaskConical className="h-3.5 w-3.5" />}>Testar restauro</Button>
                    <Button size="sm" variant="ghost" disabled={b.status === "missing"} onClick={() => download(`/api/backups/${b.filename}/download`, b.filename).catch((e) => toast.error(errorMessage(e)))} icon={<Download className="h-3.5 w-3.5" />}>Descarregar</Button>
                    <Button size="sm" variant="amber" disabled={b.status !== "ok"} onClick={() => setRestoring(b)} icon={<RotateCcw className="h-3.5 w-3.5" />}>Restaurar</Button>
                  </div>
                </div>
                {b.error && <p className="mt-1 text-xs text-danger">{b.error}</p>}
                {info[b.filename] && <p className="mt-1 text-xs text-success">{info[b.filename]}</p>}
                <p className="mt-0.5 font-mono text-[10.5px] text-muted">sha256 {b.sha256.slice(0, 16)}… · esquema {b.schema_revision}</p>
              </li>
            ))}
          </ul>
        )}
      </Panel>
      <ConfirmDialog
        open={!!restoring}
        title="Restaurar backup"
        message={<>Todos os dados actuais serão substituídos pelo conteúdo de <span className="font-mono">{restoring?.filename}</span>. Antes disso será criado um backup de segurança. Deseja continuar?</>}
        confirmLabel="Restaurar"
        loading={restore.isPending}
        onConfirm={() => restoring && restore.mutate(restoring.filename)}
        onCancel={() => setRestoring(null)}
      />
      <ConfirmDialog
        open={!!imported}
        title="Importar e restaurar"
        message={<>O ficheiro <strong>{imported?.file.name}</strong> foi validado ({imported?.counts.projects} projectos, {imported?.counts.tasks} tarefas, {imported?.counts.notes} notas). Importar substitui todos os dados actuais (é criado um backup de segurança antes).</>}
        confirmLabel="Importar"
        loading={importConfirm.isPending}
        onConfirm={() => importConfirm.mutate(undefined)}
        onCancel={() => setImported(null)}
      />
    </div>
  );
}
