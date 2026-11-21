import { Copy, KeyRound, Plus, RefreshCw, ShieldAlert, ShieldCheck, Trash2 } from "lucide-react";
import { useState } from "react";
import { api, errorMessage } from "@/api/client";
import { useApiMutation, useVault, useVaultStatus } from "@/api/hooks";
import type { SecretEntry } from "@/api/types";
import { Button, ConfirmDialog, Dialog, EmptyState, ErrorState, Field, Input, Loading, PageHeader, Panel } from "@/components/ui";
import { toast } from "@/lib/toast";
import { fmtDateTime, fmtRelative } from "@/lib/utils";

function SecretDialog({ open, onClose, entry }: { open: boolean; onClose: () => void; entry?: SecretEntry }) {
  const [form, setForm] = useState({ name: entry?.name ?? "", service: entry?.service ?? "", description: entry?.description ?? "", value: "" });
  const save = useApiMutation(
    () => {
      const body = { ...form, value: form.value || undefined };
      return entry ? api.patch(`/api/vault/${entry.id}`, body) : api.post("/api/vault", form);
    },
    { invalidate: [["vault"]], success: entry ? "Segredo actualizado." : "Segredo guardado no Keychain.", onSuccess: onClose },
  );
  const valid = form.name.trim() && (entry || form.value);
  return (
    <Dialog open={open} onClose={onClose} title={entry ? "Editar segredo" : "Novo segredo"} footer={<><Button variant="ghost" onClick={onClose}>Cancelar</Button><Button variant="primary" disabled={!valid} loading={save.isPending} onClick={() => save.mutate(undefined)}>Guardar</Button></>}>
      <div className="flex flex-col gap-3">
        <Field label="Nome" htmlFor="s-name"><Input id="s-name" autoFocus value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Token GitHub (leitura)" /></Field>
        <Field label="Serviço" htmlFor="s-svc"><Input id="s-svc" value={form.service} onChange={(e) => setForm({ ...form, service: e.target.value })} placeholder="github, anthropic, …" /></Field>
        <Field label="Descrição" htmlFor="s-desc"><Input id="s-desc" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
        <Field label={entry ? "Novo valor (deixe vazio para manter)" : "Valor"} htmlFor="s-val" hint="Enviado apenas ao backend local, que o guarda no macOS Keychain. Nunca é escrito na base de dados nem nos logs.">
          <Input id="s-val" type="password" autoComplete="off" value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} />
        </Field>
      </div>
    </Dialog>
  );
}

export default function VaultPage() {
  const status = useVaultStatus();
  const { data, isLoading, error, refetch } = useVault();
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<SecretEntry | null>(null);
  const [deleting, setDeleting] = useState<SecretEntry | null>(null);
  const del = useApiMutation((id: string) => api.del(`/api/vault/${id}`, { confirm: true }), { invalidate: [["vault"], ["integrations"]], success: "Segredo eliminado do Keychain.", onSuccess: () => setDeleting(null) });

  const copy = async (e: SecretEntry) => {
    try {
      const { value } = await api.post<{ value: string }>(`/api/vault/${e.id}/reveal`);
      await navigator.clipboard.writeText(value);
      toast.success(`«${e.name}» copiado. A área de transferência será limpa em 30 s.`);
      window.setTimeout(() => {
        void navigator.clipboard.readText().then(async (cur) => { if (cur === value) await navigator.clipboard.writeText(""); }).catch(() => undefined);
      }, 30_000);
      void refetch();
    } catch (err) {
      toast.error(errorMessage(err));
    }
  };

  const st = status.data;
  return (
    <div className="mx-auto flex max-w-[1100px] flex-col gap-4">
      <PageHeader title="Cofre de segredos" subtitle="Tokens e chaves de API. A base de dados guarda apenas metadados." actions={<Button variant="primary" disabled={!st?.available} onClick={() => setCreating(true)} icon={<Plus className="h-4 w-4" />}>Novo segredo</Button>} />
      <Panel>
        {status.isLoading ? <Loading /> : st && (
          <div className="flex items-start gap-3">
            {st.secure ? <ShieldCheck className="h-6 w-6 shrink-0 text-success" /> : <ShieldAlert className="h-6 w-6 shrink-0 text-danger" />}
            <div className="text-[13px]">
              <div className={st.secure ? "text-success" : "text-danger"}>{st.message}</div>
              <div className="mt-0.5 font-mono text-[11px] text-muted">backend: {st.backend}</div>
              <p className="mt-1 text-xs text-text-2">
                Os valores são lidos apenas por acção explícita («Copiar») ou internamente por integrações configuradas. Cada acesso fica registado no histórico (sem o valor). Os backups não incluem segredos.
              </p>
            </div>
          </div>
        )}
      </Panel>
      <Panel bodyClassName="p-0">
        {isLoading ? <div className="p-4"><Loading /></div> : error ? <div className="p-4"><ErrorState error={error} /></div> : !data?.length ? (
          <EmptyState icon={<KeyRound className="h-7 w-7" />} title="O cofre está vazio." />
        ) : (
          <table className="w-full text-left text-[13px]">
            <thead className="text-xs text-muted">
              <tr><th className="px-3 py-2 font-medium">Nome</th><th className="px-3 py-2 font-medium">Serviço</th><th className="px-3 py-2 font-medium">Identificação</th><th className="px-3 py-2 font-medium">Último acesso</th><th /></tr>
            </thead>
            <tbody>
              {data.map((e) => (
                <tr key={e.id} className="border-t border-line/60">
                  <td className="px-3 py-2.5"><div className="text-text">{e.name}</div><div className="text-xs text-muted">{e.description}</div></td>
                  <td className="px-3 py-2.5 text-text-2">{e.service || "—"}</td>
                  <td className="px-3 py-2.5 font-mono text-xs text-muted">{e.hint}</td>
                  <td className="px-3 py-2.5 text-xs text-muted" title={fmtDateTime(e.last_accessed_at)}>{e.last_accessed_at ? fmtRelative(e.last_accessed_at) : "Nunca"}</td>
                  <td className="px-3 py-2.5">
                    <div className="flex justify-end gap-1">
                      <Button size="sm" onClick={() => void copy(e)} icon={<Copy className="h-3.5 w-3.5" />}>Copiar</Button>
                      <Button size="sm" variant="ghost" onClick={() => setEditing(e)} icon={<RefreshCw className="h-3.5 w-3.5" />}>Editar</Button>
                      <Button size="icon" variant="ghost" aria-label={`Eliminar ${e.name}`} onClick={() => setDeleting(e)}><Trash2 className="h-3.5 w-3.5 text-danger" /></Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
      {creating && <SecretDialog open onClose={() => setCreating(false)} />}
      {editing && <SecretDialog open onClose={() => setEditing(null)} entry={editing} />}
      <ConfirmDialog open={!!deleting} title="Eliminar segredo" message={`Eliminar «${deleting?.name}» do Keychain? Integrações que o usem deixam de funcionar.`} confirmLabel="Eliminar" loading={del.isPending} onConfirm={() => deleting && del.mutate(deleting.id)} onCancel={() => setDeleting(null)} />
    </div>
  );
}
