import { Background, Controls, ReactFlow, type Edge, type Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { BookPlus } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "@/api/client";
import { useApiMutation, useGraph, useNotes } from "@/api/hooks";
import type { GraphEdge, GraphNode, Note, NoteKind } from "@/api/types";
import { Badge, Button, Checkbox, EmptyState, ErrorState, Loading, PageHeader, Panel, Select, Tabs } from "@/components/ui";
import { entityRoute, ENTITY_LABEL, fmtRelative, NOTE_KIND } from "@/lib/utils";

const KB_KINDS: NoteKind[] = ["concept", "solution", "decision", "error", "documentation", "idea", "reference", "lesson"];
const TYPE_COLOR: Record<string, string> = {
  note: "#22d3ee",
  project: "#d4a64a",
  task: "#3b82f6",
  checklist: "#a9b8cc",
  event: "#a9b8cc",
  automation: "#a9b8cc",
};

/** Disposição circular determinística por tipo: leve (sem simulação física) e estável. */
function layout(nodes: GraphNode[], edges: GraphEdge[]): { nodes: Node[]; edges: Edge[] } {
  const groups = new Map<string, GraphNode[]>();
  for (const n of nodes) groups.set(n.type, [...(groups.get(n.type) ?? []), n]);
  const out: Node[] = [];
  const order = ["project", "note", "task", "checklist", "event", "automation"];
  order.forEach((type, gi) => {
    const items = groups.get(type) ?? [];
    const radius = 140 + gi * 150;
    items.forEach((n, i) => {
      const a = (i / Math.max(items.length, 1)) * Math.PI * 2 + gi * 0.4;
      out.push({
        id: n.id,
        position: { x: Math.cos(a) * radius, y: Math.sin(a) * radius },
        data: { label: n.label, entity: n },
        style: {
          border: `1px solid ${TYPE_COLOR[n.type] ?? "#7a8ba3"}`,
          background: "#0f1d33",
          color: "#e6edf7",
          fontSize: 12,
          borderRadius: 8,
          padding: "6px 10px",
          width: 170,
        },
      });
    });
  });
  return {
    nodes: out,
    edges: edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      label: e.label,
      style: { stroke: e.implicit ? "rgb(212 166 74 / 0.5)" : "rgb(34 211 238 / 0.7)", strokeDasharray: e.implicit ? "4 4" : undefined },
      labelStyle: { fill: "#a9b8cc", fontSize: 10 },
      labelBgStyle: { fill: "#0b1626" },
    })),
  };
}

export default function KnowledgePage() {
  const [view, setView] = useState<"list" | "graph">("list");
  const [kind, setKind] = useState("");
  const [includeTasks, setIncludeTasks] = useState(false);
  const navigate = useNavigate();
  const notes = useNotes({ knowledge: true, kind: kind || undefined });
  const graph = useGraph(includeTasks);
  const flow = useMemo(() => (graph.data ? layout(graph.data.nodes, graph.data.edges) : null), [graph.data]);
  const create = useApiMutation(
    () => api.post<Note>("/api/notes", { title: "Novo conhecimento", kind: kind || "concept", in_knowledge_base: true }),
    { invalidate: [["notes"], ["relations"]], onSuccess: (n) => navigate(`/notes/${n.id}`) },
  );

  return (
    <div className="mx-auto max-w-[1500px]">
      <PageHeader
        title="Base de conhecimento"
        subtitle="Conceitos, soluções, decisões de arquitectura, erros resolvidos e lições aprendidas. As relações são explícitas; as ligações a projectos derivam das notas."
        actions={
          <>
            <Tabs value={view} onChange={setView} items={[{ value: "list", label: "Lista" }, { value: "graph", label: "Grafo" }]} />
            <Button variant="primary" onClick={() => create.mutate(undefined)} loading={create.isPending} icon={<BookPlus className="h-4 w-4" />}>Novo item</Button>
          </>
        }
      />
      {view === "list" ? (
        <Panel
          title="Itens"
          actions={
            <Select aria-label="Tipo" className="w-48" value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="">Todos os tipos</option>
              {KB_KINDS.map((k) => <option key={k} value={k}>{NOTE_KIND[k]}</option>)}
            </Select>
          }
        >
          {notes.isLoading ? <Loading /> : notes.error ? <ErrorState error={notes.error} /> : !notes.data?.items.length ? (
            <EmptyState title="A base de conhecimento está vazia." description="Marque uma nota como «Base de conhecimento» ou crie um novo item." />
          ) : (
            <ul className="divide-y divide-line/60">
              {notes.data.items.map((n) => (
                <li key={n.id} className="flex items-start gap-3 py-2.5">
                  <Badge tone={n.kind === "error" ? "danger" : n.kind === "decision" ? "amber" : n.kind === "solution" ? "success" : "primary"}>{NOTE_KIND[n.kind]}</Badge>
                  <div className="min-w-0 flex-1">
                    <Link to={`/notes/${n.id}`} className="text-[13px] font-medium text-text hover:text-primary">{n.title}</Link>
                    <p className="line-clamp-2 text-xs text-muted">{n.excerpt || "Sem conteúdo."}</p>
                    {n.tags.length > 0 && <div className="mt-1 flex gap-1">{n.tags.map((t) => <Badge key={t}>#{t}</Badge>)}</div>}
                  </div>
                  <span className="shrink-0 text-[11px] text-muted">{fmtRelative(n.updated_at)}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      ) : (
        <Panel title="Grafo de relações" actions={<Checkbox checked={includeTasks} onChange={setIncludeTasks} label="Incluir tarefas" />} bodyClassName="p-0">
          {graph.isLoading ? <div className="p-4"><Loading /></div> : graph.error ? <div className="p-4"><ErrorState error={graph.error} /></div> : !flow?.nodes.length ? (
            <EmptyState title="Sem itens para mostrar." description="Adicione notas à base de conhecimento e crie relações no painel «Relações» de cada nota." />
          ) : (
            <div style={{ height: "68vh" }}>
              <ReactFlow
                nodes={flow.nodes}
                edges={flow.edges}
                fitView
                nodesConnectable={false}
                onlyRenderVisibleElements
                proOptions={{ hideAttribution: true }}
                onNodeClick={(_, n) => {
                  const e = (n.data as { entity: GraphNode }).entity;
                  navigate(entityRoute(e.type, e.entity_id));
                }}
                colorMode="dark"
              >
                <Background gap={32} color="rgb(120 170 220 / 0.12)" />
                <Controls showInteractive={false} />
              </ReactFlow>
              <div className="flex flex-wrap gap-3 border-t border-line px-3 py-2 text-[11px] text-muted">
                {Object.entries(TYPE_COLOR).slice(0, 3).map(([t, c]) => (
                  <span key={t} className="inline-flex items-center gap-1"><span className="h-2 w-3 rounded-sm" style={{ border: `1px solid ${c}` }} /> {ENTITY_LABEL[t]}</span>
                ))}
                <span>— relação explícita</span><span>- - ligação derivada (nota → projecto)</span>
              </div>
            </div>
          )}
        </Panel>
      )}
    </div>
  );
}
