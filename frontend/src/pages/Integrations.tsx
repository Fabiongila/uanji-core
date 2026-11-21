import { GitBranch, PlugZap, RefreshCw } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, errorMessage } from "@/api/client";
import { useApiMutation, useIntegrations, useVault } from "@/api/hooks";
import type { IntegrationStatus, RepoOverview } from "@/api/types";
import { Badge, Button, ErrorState, Field, Input, Loading, PageHeader, Panel, Select } from "@/components/ui";
import { fmtRelative } from "@/lib/utils";

const STATUS = { not_configured: ["Não configurada", "neutral"], connected: ["Ligada", "success"], error: ["Erro", "danger"] } as const;

function GitHubCard({ it }: { it: IntegrationStatus }) {
  const vault = useVault();
  const [secret, setSecret] = useState(it.secret_id ?? "");
  const [url, setUrl] = useState("");
  const [repo, setRepo] = useState<RepoOverview | null>(null);
  const [repoErr, setRepoErr] = useState<string | null>(null);
  const configure = useApiMutation((secret_id: string | null) => api.put<IntegrationStatus>("/api/integrations/github", { secret_id }), {
    invalidate: [["integrations"]],
    success: (r) => (r.status === "connected" ? `Ligado como ${String(r.config.login)}.` : r.status === "error" ? `Erro: ${r.last_error}` : "Integração actualizada."),
  });
  const test = useApiMutation(() => api.post<IntegrationStatus>("/api/integrations/github/test"), {
    invalidate: [["integrations"]],
    success: (r) => (r.status === "connected" ? "Ligação verificada." : `Estado: ${r.last_error || r.status}`),
  });
  const query = async () => {
    setRepoErr(null);
    setRepo(null);
    try {
      setRepo(await api.post<RepoOverview>("/api/integrations/github/repo", { url }));
    } catch (e) {
      setRepoErr(errorMessage(e));
    }
  };
  const [label, tone] = STATUS[it.status];
  return (
    <Panel title={<span className="flex items-center gap-2"><GitBranch className="h-4 w-4" /> <span className="hud-label">GitHub</span></span>} actions={<Badge tone={tone}>{label}</Badge>}>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="flex flex-col gap-3 text-[13px]">
          {it.status === "connected" && <p className="text-success">Ligado como <strong>{String(it.config.login)}</strong>{it.config.name ? ` (${String(it.config.name)})` : ""}.</p>}
          {it.last_error && <p className="text-danger">{it.last_error}</p>}
          {it.last_checked_at && <p className="text-xs text-muted">Última verificação {fmtRelative(it.last_checked_at)}</p>}
          <p className="text-xs text-text-2">{it.help}</p>
          <Field label="Token (do Cofre)" htmlFor="gh-secret">
            <Select id="gh-secret" value={secret} onChange={(e) => setSecret(e.target.value)}>
              <option value="">Sem token (apenas repositórios públicos, 60 pedidos/h)</option>
              {vault.data?.map((s) => <option key={s.id} value={s.id}>{s.name} {s.hint}</option>)}
            </Select>
          </Field>
          {!vault.data?.length && <p className="text-xs text-muted">Guarde primeiro o token no <Link to="/vault" className="text-primary underline">Cofre</Link>.</p>}
          <div className="flex gap-2">
            <Button variant="primary" loading={configure.isPending} onClick={() => configure.mutate(secret || null)}>Guardar e testar</Button>
            <Button disabled={!it.has_token} loading={test.isPending} onClick={() => test.mutate(undefined)} icon={<RefreshCw className="h-3.5 w-3.5" />}>Testar ligação</Button>
          </div>
          <p className="text-[11px] text-muted">Operações suportadas: {it.capabilities.join(", ")}. Apenas leitura.</p>
        </div>
        <div>
          <div className="hud-label mb-1.5">Consultar repositório</div>
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); void query(); }}>
            <Input aria-label="URL do repositório" placeholder="https://github.com/dono/repo" value={url} onChange={(e) => setUrl(e.target.value)} />
            <Button type="submit" disabled={!url}>Consultar</Button>
          </form>
          {repoErr && <ErrorState error={new Error(repoErr)} />}
          {repo && (
            <div className="mt-2 text-xs">
              <div className="text-[13px] text-text">{repo.repo.full_name}</div>
              <p className="text-muted">{repo.repo.description}</p>
              <p className="mt-1 text-text-2">★ {repo.repo.stars} · {repo.repo.open_issues} issues/PRs · {repo.repo.language ?? "—"} · push {fmtRelative(repo.repo.pushed_at)}</p>
              <div className="hud-label mt-2">Commits recentes</div>
              <ul>{repo.commits.map((c) => <li key={c.sha} className="truncate"><span className="font-mono text-primary">{c.sha}</span> {c.message}</li>)}</ul>
              <div className="hud-label mt-2">Pull requests abertos</div>
              <ul>{repo.pull_requests.length ? repo.pull_requests.map((p) => <li key={p.number}>#{p.number} {p.title}</li>) : <li className="text-muted">Nenhum.</li>}</ul>
              <p className="mt-1 text-[10.5px] text-muted">Dados obtidos de {repo.source}.</p>
            </div>
          )}
        </div>
      </div>
    </Panel>
  );
}

export default function IntegrationsPage() {
  const { data, isLoading, error, refetch } = useIntegrations();
  return (
    <div className="mx-auto flex max-w-[1100px] flex-col gap-4">
      <PageHeader title="Integrações" subtitle="Arquitectura de adaptadores. Só são apresentadas integrações efectivamente implementadas." />
      {isLoading ? <Loading /> : error ? <ErrorState error={error} onRetry={() => void refetch()} /> : data?.map((it) => (it.provider === "github" ? <GitHubCard key={it.provider} it={it} /> : null))}
      <Panel>
        <div className="flex items-start gap-2 text-xs text-text-2">
          <PlugZap className="mt-0.5 h-4 w-4 text-primary" />
          Novas integrações implementam o contrato <code className="font-mono">IntegrationAdapter</code> (backend/uanji/integrations/base.py): estado, configuração com credencial do cofre e teste de ligação.
        </div>
      </Panel>
    </div>
  );
}
