import { Link2, X } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { useApiMutation, useRelations, useSearch } from "@/api/hooks";
import type { EntityType } from "@/api/types";
import { Input } from "@/components/ui";
import { ENTITY_LABEL, entityRoute } from "@/lib/utils";
import { useDebounced } from "@/lib/useDebounced";

/** Relações explícitas de um item com outros itens (base do grafo de conhecimento). */
export function RelationsPanel({ type, id }: { type: EntityType; id: string }) {
  const rel = useRelations(type, id);
  const [q, setQ] = useState("");
  const [label, setLabel] = useState("relacionado");
  const dq = useDebounced(q, 200);
  const search = useSearch(dq);
  const add = useApiMutation(
    (target: { entity_type: EntityType; entity_id: string }) =>
      api.post("/api/relations", { source_type: type, source_id: id, target_type: target.entity_type, target_id: target.entity_id, label }),
    { invalidate: [["relations"]], success: "Relação criada.", onSuccess: () => setQ("") },
  );
  const del = useApiMutation((rid: string) => api.del(`/api/relations/${rid}`), { invalidate: [["relations"]] });

  return (
    <div>
      <ul className="mb-2 flex flex-col gap-1">
        {rel.data?.map((r) => (
          <li key={r.id} className="flex items-center gap-2 text-[12.5px]">
            <Link2 className="h-3.5 w-3.5 shrink-0 text-primary/70" />
            <span className="shrink-0 text-muted">{r.direction === "out" ? r.label : `← ${r.label}`}</span>
            <Link to={entityRoute(r.entity_type, r.entity_id)} className="truncate text-text hover:text-primary">
              {ENTITY_LABEL[r.entity_type]}: {r.title}
            </Link>
            <button type="button" className="ml-auto" onClick={() => del.mutate(r.id)} aria-label="Remover relação">
              <X className="h-3.5 w-3.5 text-muted hover:text-danger" />
            </button>
          </li>
        ))}
        {rel.data?.length === 0 && <li className="text-xs text-muted">Sem relações.</li>}
      </ul>
      <div className="flex gap-1.5">
        <Input aria-label="Tipo de relação" className="w-28" value={label} onChange={(e) => setLabel(e.target.value)} />
        <Input aria-label="Procurar item a relacionar" placeholder="Relacionar com…" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      {dq && search.data && (
        <ul className="mt-1 max-h-40 overflow-auto rounded-md border border-line">
          {search.data.hits
            .filter((h) => !(h.entity_type === type && h.entity_id === id))
            .map((h) => (
              <li key={`${h.entity_type}:${h.entity_id}`}>
                <button
                  type="button"
                  className="block w-full truncate px-2 py-1 text-left text-xs text-text-2 hover:bg-surface-3 hover:text-text"
                  onClick={() => add.mutate({ entity_type: h.entity_type, entity_id: h.entity_id })}
                >
                  {ENTITY_LABEL[h.entity_type]}: {h.title}
                </button>
              </li>
            ))}
          {search.data.hits.length === 0 && <li className="px-2 py-1 text-xs text-muted">Sem resultados.</li>}
        </ul>
      )}
    </div>
  );
}
