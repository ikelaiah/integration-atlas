import { useEffect, useMemo, useState } from "react";
import { ArrowUpDown, Boxes, Search } from "lucide-react";
import { api } from "@/lib/api";
import type { EntityType, GraphNode, RiskFinding } from "@/lib/types";
import {
  CONFIDENCE_META,
  entityVisual,
  SEVERITY_META,
} from "@/lib/entity-visuals";
import { formatNumber } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { EmptyState, Skeleton } from "@/components/ui/misc";

export interface EntityListPageProps {
  workspaceId: string | null;
  title: string;
  description: string;
  /** Restrict to these entity types; empty means all. */
  types: EntityType[];
  risks: RiskFinding[];
  onSelect: (id: string) => void;
}

type SortKey = "name" | "type" | "degree" | "confidence" | "owner";

export function EntityListPage({
  workspaceId,
  title,
  description,
  types,
  risks,
  onSelect,
}: EntityListPageProps) {
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("degree");
  const [sortAsc, setSortAsc] = useState(false);

  useEffect(() => {
    if (!workspaceId) return;
    setLoading(true);
    api
      .graph(workspaceId, { entity_type: types.length ? types : undefined })
      .then((res) => setNodes(res.nodes))
      .catch(() => setNodes([]))
      .finally(() => setLoading(false));
  }, [workspaceId, types]);

  const riskByEntity = useMemo(() => {
    const map = new Map<string, RiskFinding[]>();
    for (const risk of risks) {
      if (!risk.entity_id) continue;
      const list = map.get(risk.entity_id) ?? [];
      list.push(risk);
      map.set(risk.entity_id, list);
    }
    return map;
  }, [risks]);

  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const filtered = needle
      ? nodes.filter(
          (n) =>
            n.name.toLowerCase().includes(needle) ||
            n.qualified_name.toLowerCase().includes(needle) ||
            n.technology.toLowerCase().includes(needle) ||
            n.owner.toLowerCase().includes(needle),
        )
      : nodes;

    const confidenceRank = (n: GraphNode) => CONFIDENCE_META[n.confidence].rank;
    const sorted = [...filtered].sort((a, b) => {
      const dir = sortAsc ? 1 : -1;
      switch (sortKey) {
        case "name":
          return dir * a.name.localeCompare(b.name);
        case "type":
          return dir * a.entity_type.localeCompare(b.entity_type);
        case "degree":
          return dir * (a.degree - b.degree);
        case "confidence":
          return dir * (confidenceRank(a) - confidenceRank(b));
        case "owner":
          return dir * (a.owner || "zzz").localeCompare(b.owner || "zzz");
        default:
          return 0;
      }
    });
    return sorted;
  }, [nodes, query, sortKey, sortAsc]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortAsc((v) => !v);
    else {
      setSortKey(key);
      setSortAsc(key === "name" || key === "owner" || key === "type");
    }
  };

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-[1180px] px-6 py-7">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-[21px] font-semibold leading-tight tracking-tight text-ink">
              {title}
            </h1>
            <p className="mt-1 max-w-[640px] text-[12px] leading-relaxed text-muted">
              {description}
            </p>
          </div>
          <div className="relative w-[240px]">
            <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-subtle" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter…"
              className="pl-8"
            />
          </div>
        </div>

        <div className="mt-5 rounded-[9px] border border-line bg-surface overflow-hidden panel-shadow">
          <div className="grid grid-cols-[1fr_150px_130px_110px_100px] items-center gap-2 border-b border-line bg-surface-2 px-3.5 py-2 text-[10px] font-semibold uppercase tracking-[0.07em] text-subtle">
            <button type="button" onClick={() => toggleSort("name")} className="flex items-center gap-1 text-left hover:text-ink">
              Name <ArrowUpDown className="h-2.5 w-2.5" />
            </button>
            <button type="button" onClick={() => toggleSort("type")} className="flex items-center gap-1 text-left hover:text-ink">
              Type <ArrowUpDown className="h-2.5 w-2.5" />
            </button>
            <button type="button" onClick={() => toggleSort("owner")} className="flex items-center gap-1 text-left hover:text-ink">
              Owner <ArrowUpDown className="h-2.5 w-2.5" />
            </button>
            <button type="button" onClick={() => toggleSort("confidence")} className="flex items-center gap-1 text-left hover:text-ink">
              Confidence <ArrowUpDown className="h-2.5 w-2.5" />
            </button>
            <button type="button" onClick={() => toggleSort("degree")} className="flex items-center gap-1 text-right hover:text-ink">
              Links <ArrowUpDown className="h-2.5 w-2.5" />
            </button>
          </div>

          {loading ? (
            <div className="space-y-1.5 p-3">
              {Array.from({ length: 8 }).map((_, i) => (
                <Skeleton key={i} className="h-[34px]" />
              ))}
            </div>
          ) : rows.length === 0 ? (
            <div className="p-6">
              <EmptyState
                icon={<Boxes className="h-5 w-5" />}
                title={query ? "No matches" : "Nothing here yet"}
                description={
                  query
                    ? `No entities match “${query}”.`
                    : "Run a scan or load the demo estate to populate this view."
                }
              />
            </div>
          ) : (
            <div>
              {rows.map((node) => {
                const visual = entityVisual(node.entity_type);
                const entityRisks = riskByEntity.get(node.id) ?? [];
                const worst = entityRisks.reduce<RiskFinding | null>(
                  (acc, r) =>
                    !acc || SEVERITY_META[r.severity].rank > SEVERITY_META[acc.severity].rank ? r : acc,
                  null,
                );
                return (
                  <button
                    key={node.id}
                    type="button"
                    onClick={() => onSelect(node.id)}
                    className="grid w-full grid-cols-[1fr_150px_130px_110px_100px] items-center gap-2 border-b border-line px-3.5 py-2 text-left transition-colors last:border-b-0 hover:bg-surface-2"
                  >
                    <div className="flex min-w-0 items-center gap-2">
                      <span
                        className="h-[7px] w-[7px] shrink-0 rounded-full"
                        style={{ backgroundColor: visual.color }}
                      />
                      <div className="min-w-0">
                        <div className="truncate text-[12px] text-ink">{node.name}</div>
                        {node.qualified_name !== node.name && (
                          <div className="truncate text-[10px] text-subtle">{node.qualified_name}</div>
                        )}
                      </div>
                      {worst && (
                        <Badge
                          size="xs"
                          dotColor={SEVERITY_META[worst.severity].color}
                          className="ml-auto shrink-0"
                        >
                          {SEVERITY_META[worst.severity].label}
                        </Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-1.5">
                      <Badge variant="subtle" size="xs" dotColor={visual.color}>
                        {visual.label}
                      </Badge>
                    </div>
                    <div className="truncate text-[11px] text-muted">
                      {node.owner || <span className="text-subtle">unowned</span>}
                    </div>
                    <div>
                      <span
                        className="text-[11px]"
                        style={{ color: CONFIDENCE_META[node.confidence].color }}
                      >
                        {CONFIDENCE_META[node.confidence].label}
                      </span>
                    </div>
                    <div className="tabular text-right text-[11px] text-muted">
                      {formatNumber(node.degree)}
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        <div className="mt-2.5 flex items-center gap-2 text-[10.5px] text-subtle">
          <span>
            {formatNumber(rows.length)} of {formatNumber(nodes.length)} entities
          </span>
          <span className="text-line-strong">·</span>
          <span>Click any row to open it in the Atlas</span>
        </div>
      </div>
    </div>
  );
}
