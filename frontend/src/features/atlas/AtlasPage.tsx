import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Download,
  Filter,
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
import type { Environment, GraphEdge, GraphNode, GraphResponse, Impact, PathResult, RelationshipType, ReviewStatus, RiskFinding } from "@/lib/types";
import {
  CONFIDENCE_META,
  ENTITY_TYPE_ORDER,
  RELATIONSHIP_META,
  entityVisual,
} from "@/lib/entity-visuals";
import { cn, formatNumber } from "@/lib/utils";
import { AtlasGraph, GraphLegend, type GraphHighlight } from "@/components/graph/AtlasGraph";
import { EntityPanel } from "@/components/panels/EntityPanel";
import { ImpactPanel, PathExplorer } from "@/components/panels/ImpactPanel";
import { PathFinderDialog } from "@/components/panels/PathFinderDialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Separator, EmptyState } from "@/components/ui/misc";

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
  const [environmentFilter, setEnvironmentFilter] = useState<Set<Environment>>(new Set());
  const [relationshipFilter, setRelationshipFilter] = useState<Set<RelationshipType>>(new Set());
  const [reviewFilter, setReviewFilter] = useState<Set<ReviewStatus>>(new Set());
  const [minConfidence, setMinConfidence] = useState<string>("");
  const [searchFilter, setSearchFilter] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [facets, setFacets] = useState<GraphResponse["facets"]>({ entity_type: {}, environment: {}, relationship_type: {}, review_status: {} });
  const [graphTruncated, setGraphTruncated] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [showMeta, setShowMeta] = useState(true);
  const [showMinimap, setShowMinimap] = useState(false);
  const [showFilters, setShowFilters] = useState(false);

  const [impact, setImpact] = useState<Impact | null>(null);
  const [impactLoading, setImpactLoading] = useState(false);
  const [pathResult, setPathResult] = useState<PathResult | null>(null);
  const [pathLoading, setPathLoading] = useState(false);
  const [pathError, setPathError] = useState<string | null>(null);
  const [pathFinderOpen, setPathFinderOpen] = useState(false);

  const [fitSignal, setFitSignal] = useState(0);
  const [focusSignal, setFocusSignal] = useState<{ id: string; zoom?: number } | undefined>();
  const requestSeq = useRef(0);
  const pathSeq = useRef(0);

  useEffect(() => {
    const timer = window.setTimeout(() => setSearchQuery(searchFilter.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [searchFilter]);

  const graphFilters = useMemo(() => ({
    entity_type: typeFilter.size ? [...typeFilter] : undefined,
    min_confidence: minConfidence || undefined,
    environment: environmentFilter.size ? [...environmentFilter] : undefined,
    relationship_type: relationshipFilter.size ? [...relationshipFilter] : undefined,
    review_status: reviewFilter.size ? [...reviewFilter] : undefined,
    q: searchQuery || undefined,
  }), [typeFilter, minConfidence, environmentFilter, relationshipFilter, reviewFilter, searchQuery]);

  const clearFilters = () => {
    setTypeFilter(new Set());
    setEnvironmentFilter(new Set());
    setRelationshipFilter(new Set());
    setReviewFilter(new Set());
    setMinConfidence("");
    setSearchFilter("");
  };

  const filterCount = typeFilter.size + environmentFilter.size + relationshipFilter.size + reviewFilter.size
    + (minConfidence ? 1 : 0) + (searchFilter ? 1 : 0);

  const downloadDiagram = async (format: "mermaid" | "plantuml") => {
    if (!workspaceId) return;
    setExportOpen(false);
    setExportError(null);
    try {
      const content = await api.graphExport(workspaceId, format, graphFilters);
      const url = URL.createObjectURL(new Blob([content], { type: "text/plain;charset=utf-8" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = `integration-atlas.${format === "mermaid" ? "mmd" : "puml"}`;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) {
      setExportError((err as Error).message);
    }
  };

  // ------------------------------------------------------------------ //
  // data
  // ------------------------------------------------------------------ //
  const loadGraph = useCallback(() => {
    if (!workspaceId) return;
    const seq = ++requestSeq.current;
    setLoading(true);
    setError(null);
    api
      .graph(workspaceId, graphFilters)
      .then((res) => {
        if (seq !== requestSeq.current) return;
        setNodes(res.nodes);
        setEdges(res.edges);
        setFacets(res.facets);
        setGraphTruncated(res.truncated);
      })
      .catch((err: Error) => { if (seq === requestSeq.current) setError(err.message); })
      .finally(() => { if (seq === requestSeq.current) setLoading(false); });
  }, [workspaceId, graphFilters]);

  useEffect(() => {
    loadGraph();
  }, [loadGraph]);

  // ------------------------------------------------------------------ //
  // derived
  // ------------------------------------------------------------------ //
  const typeCounts = facets.entity_type;
  const visibleNodes = useMemo(() => {
    if (panel?.kind !== "path" || !pathResult?.found) return nodes;
    const byId = new Map(nodes.map((node) => [node.id, node]));
    for (const step of pathResult.steps) byId.set(step.entity.id, step.entity);
    return [...byId.values()];
  }, [nodes, panel, pathResult]);
  const visibleEdges = useMemo(() => {
    if (panel?.kind !== "path" || !pathResult?.found) return edges;
    const byId = new Map(edges.map((edge) => [edge.id, edge]));
    for (const step of pathResult.steps) {
      if (step.relationship) byId.set(step.relationship.id, step.relationship);
    }
    return [...byId.values()];
  }, [edges, panel, pathResult]);

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
      const edgeIds = new Set(pathResult.steps.flatMap((step) =>
        step.relationship ? [step.relationship.id] : []));
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

  // Escape closes the topmost surface first.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        if (pathFinderOpen) {
          setPathFinderOpen(false);
          return;
        }
        if (exportOpen) {
          setExportOpen(false);
          return;
        }
        pathSeq.current += 1;
        setPanel(null);
        setSelectedId(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pathFinderOpen, exportOpen]);

  // cross-page events dispatched from the top bar / command palette
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
            {graphTruncated && <Badge variant="warning" size="xs" title="The graph is capped at 2,000 nodes; exports use the same view.">Limited view</Badge>}
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
              showFilters || filterCount > 0
                ? "border-accent/40 bg-accent-soft text-accent-strong"
                : "border-line-strong text-ink-muted hover:text-ink hover:bg-surface-2",
            )}
          >
            <SlidersHorizontal className="h-3 w-3" />
            Filters
            {filterCount > 0 && (
              <span className="tabular rounded-[3px] bg-accent/25 px-1 text-[9px]">
                {filterCount}
              </span>
            )}
          </button>

          <div className="ml-auto flex items-center gap-1">
            <div className="relative">
              <Button variant="outline" size="xs" disabled={loading || !workspaceId} onClick={() => setExportOpen((value) => !value)} aria-expanded={exportOpen} title="Download the filtered graph; a temporary path overlay is excluded">
                <Download className="h-3 w-3" /> Export
              </Button>
              {exportOpen && <div className="absolute right-0 top-8 z-50 min-w-[150px] rounded-[6px] border border-line-strong bg-surface p-1 panel-shadow">
                <button type="button" onClick={() => downloadDiagram("mermaid")} className="w-full rounded-[4px] px-2 py-1.5 text-left text-[11.5px] text-ink hover:bg-surface-2">Mermaid (.mmd)</button>
                <button type="button" onClick={() => downloadDiagram("plantuml")} className="w-full rounded-[4px] px-2 py-1.5 text-left text-[11.5px] text-ink hover:bg-surface-2">PlantUML (.puml)</button>
              </div>}
            </div>
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
                clearFilters();
                setFitSignal((n) => n + 1);
              }}
            >
              <RotateCcw className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>

        {exportError && <div role="alert" className="border-b border-danger/30 bg-danger/10 px-3 py-1.5 text-[11px] text-danger">Export failed: {exportError}</div>}

        {/* filter drawer */}
        {showFilters && (
          <div className="flex max-h-[190px] flex-wrap items-center gap-2 overflow-y-auto border-b border-line bg-surface-2 px-3 py-2.5 fade-in">
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
                  aria-pressed={active}
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
                  aria-pressed={minConfidence === key}
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

            <Separator orientation="vertical" className="mx-1 h-4" />
            <span className="text-[10px] uppercase tracking-[0.07em] text-subtle">Environment</span>
            {(["production", "test", "development", "unknown"] as Environment[])
              .filter((value) => facets.environment[value])
              .map((value) => <button key={value} type="button" aria-pressed={environmentFilter.has(value)}
                onClick={() => setEnvironmentFilter((previous) => toggleSet(previous, value))}
                className={filterChipClass(environmentFilter.has(value))}>
                {value} <span className="tabular opacity-70">{facets.environment[value]}</span>
              </button>)}

            <Separator orientation="vertical" className="mx-1 h-4" />
            <span className="text-[10px] uppercase tracking-[0.07em] text-subtle">Relationship</span>
            {(Object.keys(facets.relationship_type) as RelationshipType[]).sort().map((value) =>
              <button key={value} type="button" aria-pressed={relationshipFilter.has(value)}
                onClick={() => setRelationshipFilter((previous) => toggleSet(previous, value))}
                className={filterChipClass(relationshipFilter.has(value))}>
                {RELATIONSHIP_META[value]?.label ?? value.replaceAll("_", " ")}
                <span className="tabular opacity-70">{facets.relationship_type[value]}</span>
              </button>)}

            <Separator orientation="vertical" className="mx-1 h-4" />
            <span className="text-[10px] uppercase tracking-[0.07em] text-subtle">Review</span>
            {(["proposed", "confirmed", "rejected"] as ReviewStatus[]).map((value) =>
              <button key={value} type="button" aria-pressed={reviewFilter.has(value)}
                onClick={() => setReviewFilter((previous) => toggleSet(previous, value))}
                className={filterChipClass(reviewFilter.has(value))}>
                {value} <span className="tabular opacity-70">{facets.review_status[value] ?? 0}</span>
              </button>)}

            {filterCount > 0 && (
              <Button
                variant="ghost"
                size="xs"
                onClick={clearFilters}
              >
                <RotateCcw className="h-3 w-3" /> Clear all
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
                title={Object.keys(facets.entity_type).length ? "No entities match these filters" : "Nothing discovered yet"}
                description={Object.keys(facets.entity_type).length
                  ? "Try clearing filters or widening your search."
                  : "Load the Northstar demo or run a scan to populate the atlas."}
                action={Object.keys(facets.entity_type).length
                  ? <Button variant="outline" size="sm" onClick={clearFilters}>Clear all filters</Button>
                  : <Button variant="default" size="sm" onClick={() => api.workspaces.seedDemo().then(loadGraph)}>Load demo estate</Button>}
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
          onUpdated={loadGraph}
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
          error={pathError}
          onEdit={() => setPathFinderOpen(true)}
          onClose={() => {
            pathSeq.current += 1;
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

      <PathFinderDialog
        workspaceId={workspaceId}
        open={pathFinderOpen}
        onClose={() => setPathFinderOpen(false)}
        onFind={(sourceId, targetId) => {
          const seq = ++pathSeq.current;
          setPanel({ kind: "path", sourceId, targetId });
          setPathLoading(true);
          setPathResult(null);
          setPathError(null);
          if (!workspaceId) return;
          api
            .path(workspaceId, sourceId, targetId)
            .then((res) => { if (seq === pathSeq.current) setPathResult(res); })
            .catch((err: Error) => { if (seq === pathSeq.current) setPathError(err.message); })
            .finally(() => { if (seq === pathSeq.current) setPathLoading(false); });
        }}
      />
    </div>
  );
}

function toggleSet<T>(previous: Set<T>, value: T): Set<T> {
  const next = new Set(previous);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return next;
}

function filterChipClass(active: boolean): string {
  return cn(
    "inline-flex items-center gap-1.5 rounded-[4px] border px-1.5 py-[3px] text-[10.5px] capitalize transition-colors",
    active ? "border-accent/40 bg-accent-soft text-accent-strong"
      : "border-line-strong text-ink-muted hover:text-ink",
  );
}
