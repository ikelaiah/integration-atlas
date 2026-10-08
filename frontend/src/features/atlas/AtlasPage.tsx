import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Filter,
  GitBranch,
  Loader2,
  Maximize2,
  Minus,
  Network,
  Plus,
  Radar,
  RotateCcw,
  Search,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { api } from "@/lib/api";
import type { GraphEdge, GraphNode, Impact, PathResult, RiskFinding } from "@/lib/types";
import {
  CONFIDENCE_META,
  ENTITY_TYPE_ORDER,
  entityVisual,
} from "@/lib/entity-visuals";
import { cn, formatNumber } from "@/lib/utils";
import { AtlasGraph, GraphLegend, type GraphHighlight } from "@/components/graph/AtlasGraph";
import { EntityPanel } from "@/components/panels/EntityPanel";
import { ImpactPanel, PathExplorer } from "@/components/panels/ImpactPanel";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Separator, EmptyState, Kbd } from "@/components/ui/misc";

type SidePanel =
  | { kind: "entity"; id: string }
  | { kind: "impact"; id: string; direction: "downstream" | "upstream" }
  | { kind: "path"; sourceId: string; targetId: string }
  | null;

export function AtlasPage({ workspaceId, risks }: { workspaceId: string | null; risks: RiskFinding[] }) {
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [panel, setPanel] = useState<SidePanel>(null);

  const [typeFilter, setTypeFilter] = useState<Set<string>>(new Set());
  const [minConfidence, setMinConfidence] = useState<string>("");
  const [searchFilter, setSearchFilter] = useState("");
  const [showMeta, setShowMeta] = useState(true);
  const [showMinimap, setShowMinimap] = useState(false);
  const [showFilters, setShowFilters] = useState(false);

  const [impact, setImpact] = useState<Impact | null>(null);
  const [impactLoading, setImpactLoading] = useState(false);
  const [pathResult, setPathResult] = useState<PathResult | null>(null);
  const [pathLoading, setPathLoading] = useState(false);

  const [fitSignal, setFitSignal] = useState(0);
  const [focusSignal, setFocusSignal] = useState<{ id: string; zoom?: number } | undefined>();

  // ------------------------------------------------------------------ //
  // data
  // ------------------------------------------------------------------ //
  const loadGraph = useCallback(() => {
    if (!workspaceId) return;
    setLoading(true);
    setError(null);
    api
      .graph(workspaceId, {
        entity_type: typeFilter.size ? [...typeFilter] : undefined,
        min_confidence: minConfidence || undefined,
      })
      .then((res) => {
        setNodes(res.nodes);
        setEdges(res.edges);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [workspaceId, typeFilter, minConfidence]);

  useEffect(() => {
    loadGraph();
  }, [loadGraph]);

  // ------------------------------------------------------------------ //
  // derived
  // ------------------------------------------------------------------ //
  const typeCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const node of nodes) counts[node.entity_type] = (counts[node.entity_type] ?? 0) + 1;
    return counts;
  }, [nodes]);

  const visibleNodes = useMemo(() => {
    const needle = searchFilter.trim().toLowerCase();
    if (!needle) return nodes;
    return nodes.filter(
      (n) =>
        n.name.toLowerCase().includes(needle) ||
        n.qualified_name.toLowerCase().includes(needle) ||
        n.technology.toLowerCase().includes(needle),
    );
  }, [nodes, searchFilter]);

  const visibleIds = useMemo(() => new Set(visibleNodes.map((n) => n.id)), [visibleNodes]);

  const visibleEdges = useMemo(
    () => edges.filter((e) => visibleIds.has(e.flow_from) && visibleIds.has(e.flow_to)),
    [edges, visibleIds],
  );

  // ------------------------------------------------------------------ //
  // highlight computation
  // ------------------------------------------------------------------ //
  const highlight: GraphHighlight | null = useMemo(() => {
    if (panel?.kind === "impact" && impact) {
      const impactIds = new Set(impact.groups.flatMap((g) => g.entities.map((e) => e.id)));
      const focusIds = new Set([impact.root.id, ...impactIds]);
      const edgeIds = new Set<string>();
      for (const edge of edges) {
        if (focusIds.has(edge.source_id) && focusIds.has(edge.target_id)) edgeIds.add(edge.id);
      }
      return { focusIds, edgeIds, impactIds, rootId: impact.root.id };
    }

    if (panel?.kind === "path" && pathResult?.found) {
      const pathIds = new Set(pathResult.steps.map((s) => s.entity.id));
      const edgeIds = new Set<string>();
      for (const edge of edges) {
        if (pathIds.has(edge.source_id) && pathIds.has(edge.target_id)) edgeIds.add(edge.id);
      }
      return {
        focusIds: pathIds,
        edgeIds,
        impactIds: new Set(),
        rootId: pathResult.steps[0]?.entity.id,
        pathIds,
      };
    }

    return null;
  }, [panel, impact, pathResult, edges]);

  // ------------------------------------------------------------------ //
  // interactions
  // ------------------------------------------------------------------ //
  const handleSelect = useCallback((id: string | null) => {
    setSelectedId(id);
    if (!id) {
      setPanel(null);
      return;
    }
    setPanel({ kind: "entity", id });
  }, []);

  const handleImpact = useCallback(
    (id: string, direction: "downstream" | "upstream") => {
      if (!workspaceId) return;
      setPanel({ kind: "impact", id, direction });
      setImpactLoading(true);
      setImpact(null);
      api
        .impact(workspaceId, id, { direction })
        .then((res) => setImpact(res))
        .catch(() => setImpact(null))
        .finally(() => setImpactLoading(false));
    },
    [workspaceId],
  );

  const handleChangeDirection = useCallback(
    (direction: "downstream" | "upstream") => {
      if (panel?.kind !== "impact") return;
      handleImpact(panel.id, direction);
    },
    [panel, handleImpact],
  );

  const handleFocus = useCallback(
    (id: string) => {
      setFocusSignal({ id, zoom: 1.02 });
    },
    [],
  );

  // keyboard: Esc closes the panel
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setPanel(null);
        setSelectedId(null);
        setPathFinderOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // cross-page events dispatched from the top bar / command palette
  const [pathFinderOpen, setPathFinderOpen] = useState(false);
  useEffect(() => {
    const onSelect = (event: Event) => {
      const id = (event as CustomEvent<string>).detail;
      if (!id) return;
      setSelectedId(id);
      setPanel({ kind: "entity", id });
      setFocusSignal({ id, zoom: 1.02 });
    };
    const onImpact = (event: Event) => {
      const id = (event as CustomEvent<string>).detail;
      if (id) handleImpact(id, "downstream");
    };
    const onOpenPath = () => {
      setPathFinderOpen(true);
    };
    const onOpenImpact = () => {
      if (selectedId) handleImpact(selectedId, "downstream");
    };

    window.addEventListener("atlas:select", onSelect);
    window.addEventListener("atlas:impact", onImpact);
    window.addEventListener("atlas:open-path-finder", onOpenPath);
    window.addEventListener("atlas:open-impact", onOpenImpact);
    return () => {
      window.removeEventListener("atlas:select", onSelect);
      window.removeEventListener("atlas:impact", onImpact);
      window.removeEventListener("atlas:open-path-finder", onOpenPath);
      window.removeEventListener("atlas:open-impact", onOpenImpact);
    };
  }, [handleImpact, selectedId]);

  // ------------------------------------------------------------------ //
  // render
  // ------------------------------------------------------------------ //
  return (
    <div className="flex h-full min-w-0 flex-1">
      <div className="flex min-w-0 flex-1 flex-col">
        {/* toolbar */}
        <div className="flex h-[46px] shrink-0 items-center gap-2 border-b border-line bg-surface px-3">
          <div className="flex items-center gap-1.5">
            <Network className="h-3.5 w-3.5 text-accent-strong" />
            <span className="text-[12px] font-semibold text-ink">Integration Atlas</span>
            <Badge variant="subtle" size="xs">
              {formatNumber(visibleNodes.length)} nodes · {formatNumber(visibleEdges.length)} edges
            </Badge>
          </div>

          <div className="relative ml-2 w-[190px]">
            <Search className="absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-subtle" />
            <Input
              value={searchFilter}
              onChange={(e) => setSearchFilter(e.target.value)}
              placeholder="Filter nodes…"
              className="h-7 pl-7 text-[11.5px]"
            />
            {searchFilter && (
              <button
                type="button"
                onClick={() => setSearchFilter("")}
                className="absolute right-1.5 top-1/2 -translate-y-1/2 text-subtle hover:text-ink"
              >
                <X className="h-3 w-3" />
              </button>
            )}
          </div>

          <button
            type="button"
            onClick={() => setShowFilters((v) => !v)}
            className={cn(
              "inline-flex h-7 items-center gap-1.5 rounded-[5px] border px-2 text-[11.5px] transition-colors",
              showFilters || typeFilter.size > 0 || minConfidence
                ? "border-accent/40 bg-accent-soft text-accent-strong"
                : "border-line-strong text-ink-muted hover:text-ink hover:bg-surface-2",
            )}
          >
            <SlidersHorizontal className="h-3 w-3" />
            Filters
            {(typeFilter.size > 0 || minConfidence) && (
              <span className="tabular rounded-[3px] bg-accent/25 px-1 text-[9px]">
                {typeFilter.size + (minConfidence ? 1 : 0)}
              </span>
            )}
          </button>

          <div className="ml-auto flex items-center gap-1">
            <Button
              variant={showMeta ? "subtle" : "ghost"}
              size="xs"
              onClick={() => setShowMeta((v) => !v)}
              title="Toggle node metadata"
            >
              Meta
            </Button>
            <Button
              variant={showMinimap ? "subtle" : "ghost"}
              size="xs"
              onClick={() => setShowMinimap((v) => !v)}
              title="Toggle minimap"
            >
              Map
            </Button>
            <Separator orientation="vertical" className="mx-0.5 h-4" />
            <Button variant="ghost" size="iconSm" title="Zoom in" onClick={() => setFitSignal((n) => n + 1)}>
              <Plus className="h-3.5 w-3.5" />
            </Button>
            <Button variant="ghost" size="iconSm" title="Zoom out">
              <Minus className="h-3.5 w-3.5" />
            </Button>
            <Button variant="ghost" size="iconSm" title="Fit to view" onClick={() => setFitSignal((n) => n + 1)}>
              <Maximize2 className="h-3.5 w-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="iconSm"
              title="Reset view"
              onClick={() => {
                setPanel(null);
                setSelectedId(null);
                setTypeFilter(new Set());
                setMinConfidence("");
                setSearchFilter("");
                setFitSignal((n) => n + 1);
              }}
            >
              <RotateCcw className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>

        {/* filter drawer */}
        {showFilters && (
          <div className="flex flex-wrap items-center gap-2 border-b border-line bg-surface-2 px-3 py-2.5 fade-in">
            <div className="flex items-center gap-1.5">
              <Filter className="h-3 w-3 text-subtle" />
              <span className="text-[10px] uppercase tracking-[0.07em] text-subtle">Type</span>
            </div>
            {ENTITY_TYPE_ORDER.filter((t) => typeCounts[t]).map((type) => {
              const active = typeFilter.has(type);
              const visual = entityVisual(type);
              return (
                <button
                  key={type}
                  type="button"
                  onClick={() =>
                    setTypeFilter((prev) => {
                      const next = new Set(prev);
                      if (next.has(type)) next.delete(type);
                      else next.add(type);
                      return next;
                    })
                  }
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-[4px] border px-1.5 py-[3px] text-[10.5px] transition-colors",
                    active
                      ? "border-accent/40 bg-accent-soft text-accent-strong"
                      : "border-line-strong text-ink-muted hover:text-ink",
                  )}
                >
                  <span className="h-[5px] w-[5px] rounded-full" style={{ backgroundColor: visual.color }} />
                  {visual.label}
                  <span className="tabular text-[9px] opacity-70">{typeCounts[type]}</span>
                </button>
              );
            })}

            <Separator orientation="vertical" className="mx-1 h-4" />

            <span className="text-[10px] uppercase tracking-[0.07em] text-subtle">Confidence</span>
            <div className="flex items-center gap-1">
              {(Object.keys(CONFIDENCE_META) as (keyof typeof CONFIDENCE_META)[]).map((key) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setMinConfidence(minConfidence === key ? "" : key)}
                  className={cn(
                    "rounded-[4px] border px-1.5 py-[3px] text-[10.5px] transition-colors",
                    minConfidence === key
                      ? "border-accent/40 bg-accent-soft text-accent-strong"
                      : "border-line-strong text-ink-muted hover:text-ink",
                  )}
                >
                  {CONFIDENCE_META[key].label}+
                </button>
              ))}
            </div>

            {(typeFilter.size > 0 || minConfidence) && (
              <Button
                variant="ghost"
                size="xs"
                onClick={() => {
                  setTypeFilter(new Set());
                  setMinConfidence("");
                }}
              >
                <RotateCcw className="h-3 w-3" /> Clear
              </Button>
            )}
          </div>
        )}

        {/* canvas */}
        <div className="relative min-h-0 flex-1">
          {loading ? (
            <div className="flex h-full items-center justify-center">
              <div className="flex flex-col items-center gap-2.5">
                <Loader2 className="h-5 w-5 animate-spin text-accent-strong" />
                <div className="text-[12px] text-muted">Loading the integration graph…</div>
              </div>
            </div>
          ) : error ? (
            <div className="flex h-full items-center justify-center p-8">
              <EmptyState
                title="Could not load the graph"
                description={error}
                action={
                  <Button variant="outline" size="sm" onClick={loadGraph}>
                    Try again
                  </Button>
                }
              />
            </div>
          ) : nodes.length === 0 ? (
            <div className="flex h-full items-center justify-center p-8">
              <EmptyState
                icon={<Network className="h-6 w-6" />}
                title="Nothing discovered yet"
                description="Load the Northstar demo or run a scan to populate the atlas."
                action={
                  <Button
                    variant="default"
                    size="sm"
                    onClick={() => api.workspaces.seedDemo().then(loadGraph)}
                  >
                    Load demo estate
                  </Button>
                }
              />
            </div>
          ) : (
            <AtlasGraph
              nodes={visibleNodes}
              edges={visibleEdges}
              selectedId={selectedId}
              hoveredId={hoveredId}
              highlight={highlight}
              showMeta={showMeta}
              showMinimap={showMinimap}
              onSelect={handleSelect}
              onHover={setHoveredId}
              onEdgeSelect={(edge) => handleSelect(edge.flow_from)}
              fitSignal={fitSignal}
              focusSignal={focusSignal}
            />
          )}

          {/* floating legend */}
          <div className="pointer-events-auto absolute left-3 top-3 z-10 max-w-[560px] rounded-[8px] border border-line bg-surface/92 px-2.5 py-2 backdrop-blur-sm panel-shadow">
            <GraphLegend
              counts={typeCounts}
              activeTypes={typeFilter}
              onToggle={(type) =>
                setTypeFilter((prev) => {
                  const next = new Set(prev);
                  if (next.has(type)) next.delete(type);
                  else next.add(type);
                  return next;
                })
              }
            />
            <div className="mt-1.5 flex items-center gap-2 border-t border-line pt-1.5 text-[9.5px] text-subtle">
              <span>Arrows show influence direction</span>
              <span className="text-line-strong">·</span>
              <span>hover to dim unrelated</span>
              <span className="text-line-strong">·</span>
              <span>click to inspect</span>
            </div>
          </div>

          {/* impact hint */}
          {panel?.kind === "impact" && impact && (
            <div className="pointer-events-none absolute bottom-3 left-1/2 z-10 -translate-x-1/2">
              <div className="pointer-events-auto flex items-center gap-2 rounded-[7px] border border-accent/35 bg-surface/95 px-3 py-1.5 backdrop-blur-sm">
                <Radar className="h-3.5 w-3.5 text-accent-strong" />
                <span className="text-[11px] text-ink">
                  <span className="font-semibold">{impact.root.name}</span> can affect{" "}
                  <span className="font-semibold text-accent-strong">
                    {formatNumber(impact.total_affected)}
                  </span>{" "}
                  entities
                </span>
                <Button variant="ghost" size="xs" onClick={() => { setPanel(null); setImpact(null); }}>
                  <X className="h-3 w-3" />
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* right-hand panel */}
      {panel?.kind === "entity" && (
        <EntityPanel
          entityId={panel.id}
          risks={risks}
          onClose={() => {
            setPanel(null);
            setSelectedId(null);
          }}
          onSelectEntity={(id) => {
            setSelectedId(id);
            setPanel({ kind: "entity", id });
            setFocusSignal({ id, zoom: 1.02 });
          }}
          onImpact={handleImpact}
          onFocus={handleFocus}
        />
      )}

      {panel?.kind === "impact" && (
        <ImpactPanel
          impact={impact}
          loading={impactLoading}
          onClose={() => {
            setPanel(null);
            setImpact(null);
          }}
          onSelectEntity={(id) => {
            setSelectedId(id);
            setPanel({ kind: "entity", id });
            setFocusSignal({ id, zoom: 1.02 });
          }}
          onChangeDirection={handleChangeDirection}
        />
      )}

      {panel?.kind === "path" && (
        <PathExplorer
          result={pathResult}
          loading={pathLoading}
          candidates={nodes.slice(0, 20)}
          onClose={() => {
            setPanel(null);
            setPathResult(null);
          }}
          onSelectEntity={(id) => {
            setSelectedId(id);
            setPanel({ kind: "entity", id });
            setFocusSignal({ id, zoom: 1.02 });
          }}
        />
      )}

      <PathFinderInline
        nodes={nodes}
        open={pathFinderOpen}
        onClose={() => setPathFinderOpen(false)}
        onFind={(sourceId, targetId) => {
          setPanel({ kind: "path", sourceId, targetId });
          setPathLoading(true);
          setPathResult(null);
          if (!workspaceId) return;
          api
            .path(workspaceId, sourceId, targetId)
            .then((res) => setPathResult(res))
            .catch(() => setPathResult(null))
            .finally(() => setPathLoading(false));
        }}
      />
    </div>
  );
}

/** Compact path finder dialog used from the top bar. */
export function PathFinderInline({
  nodes,
  open,
  onClose,
  onFind,
}: {
  nodes: GraphNode[];
  open: boolean;
  onClose: () => void;
  onFind: (sourceId: string, targetId: string) => void;
}) {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [fromQuery, setFromQuery] = useState("");
  const [toQuery, setToQuery] = useState("");

  if (!open) return null;

  const matches = (query: string, exclude: string) =>
    nodes
      .filter(
        (n) =>
          n.id !== exclude &&
          (n.name.toLowerCase().includes(query.toLowerCase()) ||
            n.qualified_name.toLowerCase().includes(query.toLowerCase())),
      )
      .slice(0, 8);

  return (
    <div
      className="fixed inset-0 z-[92] flex items-start justify-center bg-black/55 pt-[16vh]"
      onClick={onClose}
    >
      <div
        className="w-full max-w-[420px] rounded-[10px] border border-line-strong bg-surface p-4 float-shadow"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2">
          <GitBranch className="h-4 w-4 text-accent-strong" />
          <div className="text-[13px] font-semibold text-ink">Find dependency path</div>
          <button onClick={onClose} className="ml-auto text-subtle hover:text-ink">
            <X className="h-3.5 w-3.5" />
          </button>
        </div>

        <div className="mt-3 space-y-2.5">
          <div>
            <div className="text-[10px] uppercase tracking-[0.07em] text-subtle">From</div>
            <Input
              value={fromQuery}
              onChange={(e) => {
                setFromQuery(e.target.value);
                setFrom("");
              }}
              placeholder="e.g. LegacySIS"
              className="mt-1"
            />
            {fromQuery && !from && (
              <div className="mt-1 max-h-[130px] overflow-y-auto rounded-[5px] border border-line">
                {matches(fromQuery, to).map((node) => (
                  <button
                    key={node.id}
                    type="button"
                    onClick={() => {
                      setFrom(node.id);
                      setFromQuery(node.name);
                    }}
                    className="flex w-full items-center gap-2 px-2 py-1 text-left hover:bg-surface-2"
                  >
                    <span
                      className="h-[6px] w-[6px] rounded-full"
                      style={{ backgroundColor: entityVisual(node.entity_type).color }}
                    />
                    <span className="truncate text-[11.5px] text-ink">{node.name}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          <div>
            <div className="text-[10px] uppercase tracking-[0.07em] text-subtle">To</div>
            <Input
              value={toQuery}
              onChange={(e) => {
                setToQuery(e.target.value);
                setTo("");
              }}
              placeholder="e.g. EnrolmentPortal"
              className="mt-1"
            />
            {toQuery && !to && (
              <div className="mt-1 max-h-[130px] overflow-y-auto rounded-[5px] border border-line">
                {matches(toQuery, from).map((node) => (
                  <button
                    key={node.id}
                    type="button"
                    onClick={() => {
                      setTo(node.id);
                      setToQuery(node.name);
                    }}
                    className="flex w-full items-center gap-2 px-2 py-1 text-left hover:bg-surface-2"
                  >
                    <span
                      className="h-[6px] w-[6px] rounded-full"
                      style={{ backgroundColor: entityVisual(node.entity_type).color }}
                    />
                    <span className="truncate text-[11.5px] text-ink">{node.name}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="mt-4 flex items-center gap-2">
          <Button
            variant="default"
            size="sm"
            disabled={!from || !to}
            onClick={() => {
              onFind(from, to);
              onClose();
            }}
          >
            <GitBranch className="h-3 w-3" /> Find path
          </Button>
          <Button variant="ghost" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <span className="ml-auto text-[10px] text-subtle">
            <Kbd>esc</Kbd> to close
          </span>
        </div>
      </div>
    </div>
  );
}
