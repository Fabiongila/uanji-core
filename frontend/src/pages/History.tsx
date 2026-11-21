import { useState } from "react";
import { Link } from "react-router-dom";
import { useActivity } from "@/api/hooks";
import { Button, EmptyState, ErrorState, Loading, PageHeader, Panel, Select } from "@/components/ui";
import { ENTITY_LABEL, entityRoute, fmtDateTime } from "@/lib/utils";

const PAGE = 100;

export default function HistoryPage() {
  const [type, setType] = useState("");
  const [page, setPage] = useState(0);
  const { data, isLoading, error, refetch } = useActivity({ entity_type: type || undefined, limit: PAGE, offset: page * PAGE });
  return (
    <div className="mx-auto max-w-[1200px]">
      <PageHeader
        title="Histórico"
        subtitle="Registo de alterações e acções sensíveis. Os valores de segredos nunca são registados."
        actions={
          <Select aria-label="Tipo" className="w-44" value={type} onChange={(e) => { setType(e.target.value); setPage(0); }}>
            <option value="">Todos os tipos</option>
            {Object.entries(ENTITY_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </Select>
        }
      />
      <Panel>
        {isLoading ? <Loading /> : error ? <ErrorState error={error} onRetry={() => void refetch()} /> : !data?.length ? <EmptyState title="Sem registos." /> : (
          <ul>
            {data.map((a) => (
              <li key={a.id} className="flex gap-3 border-b border-line/50 py-2 text-[13px] last:border-0">
                <span className="w-36 shrink-0 font-mono text-[11px] text-muted">{fmtDateTime(a.created_at)}</span>
                <span className="w-24 shrink-0 text-[11px] uppercase tracking-wide text-primary/80">{ENTITY_LABEL[a.entity_type] ?? a.entity_type}</span>
                {["project", "task", "note", "automation", "checklist", "event"].includes(a.entity_type) && a.action !== "deleted" ? (
                  <Link to={entityRoute(a.entity_type, a.entity_id)} className="text-text-2 hover:text-text">{a.summary}</Link>
                ) : (
                  <span className="text-text-2">{a.summary}</span>
                )}
              </li>
            ))}
          </ul>
        )}
        <div className="mt-3 flex justify-between">
          <Button size="sm" variant="ghost" disabled={page === 0} onClick={() => setPage(page - 1)}>Mais recentes</Button>
          <Button size="sm" variant="ghost" disabled={(data?.length ?? 0) < PAGE} onClick={() => setPage(page + 1)}>Mais antigos</Button>
        </div>
      </Panel>
    </div>
  );
}
