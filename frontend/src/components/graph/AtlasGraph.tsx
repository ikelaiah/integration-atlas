import { useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type NodeMouseHandler,
  type EdgeMouseHandler,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import type { GraphEdge, GraphNode } from "@/lib/types";
import { entityVisual, RELATIONSHIP_META, CONFIDENCE_META } from "@/lib/entity-visuals";
import { layoutGraph } from "@/lib/layout";
import { cn, truncate } from "@/lib/utils";
import { EntityNode, type EntityFlowNode } from "./EntityNode";

export type GraphMode = "explore" | "impact" | "upstream" | "path" | "neighbours";

export interface GraphHighlight {
  /** Nodes that stay fully visible; everything else fades. */
  focusIds: Set<string>;
  /** Edges that get the accent treatment. */
  edgeIds: Set<string>;
  /** Node ids rendered with the "impact" styling. */
  impactIds: Set<string>;
  rootId?: string;
  pathIds?: Set<string>;
}

export interface AtlasGraphProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selectedId: string | null;
  hoveredId: string | null;
  highlight: GraphHighlight | null;
  showMeta: boolean;
  showMinimap: boolean;
  onSelect: (id: string | null) => void;
  onHover: (id: string | null) => void;
  onEdgeSelect?: (edge: GraphEdge) => void;
  fitSignal?: number;
  focusSignal?: { id: string; zoom?: number };
  className?: string;
}

function buildFlowState(
  node: GraphNode,
  ctx: {
    selectedId: string | null;
    hoveredId: string | null;
    highlight: GraphHighlight | null;
    neighbours: Set<string>;
  },
): "default" | "selected" | "highlight" | "dimmed" | "impact" | "path" | "root" {
  const { selectedId, hoveredId, highlight, neighbours } = ctx;
  if (highlight) {
    if (highlight.rootId === node.id) return "root";
    if (highlight.pathIds?.has(node.id)) return "path";
    if (highlight.impactIds.has(node.id)) return "impact";
    if (highlight.focusIds.has(node.id)) return "highlight";
    return "dimmed";
  }
  if (hoveredId && hoveredId !== node.id && !neighbours.has(node.id)) return "dimmed";
  if (hoveredId && (hoveredId === node.id || neighbours.has(node.id))) return "highlight";
  if (selectedId === node.id) return "selected";
  return "default";
}

function AtlasGraphInner(props: AtlasGraphProps) {
  const {
    nodes,
    edges,
    selectedId,
    hoveredId,
    highlight,
    showMeta,
    showMinimap,
    onSelect,
    onHover,
    onEdgeSelect,
    fitSignal,
    focusSignal,
    className,
  } = props;

  const flow = useReactFlow();
  const containerRef = useRef<HTMLDivElement>(null);
  const [dims, setDims] = useState({ width: 1200, height: 800 });

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver(() => {
      setDims({ width: el.clientWidth, height: el.clientHeight });
    });
    observer.observe(el);
    setDims({ width: el.clientWidth, height: el.clientHeight });
    return () => observer.disconnect();
  }, []);

  const layout = useMemo(() => {
    const wide = dims.width > 900;
    return layoutGraph(nodes, edges, {
      nodeWidth: wide ? 200 : 170,
      layerGap: wide ? 118 : 88,
      rankGap: 26,
    });
  }, [nodes, edges, dims.width]);

  const neighbourMap = useMemo(() => {
    const map = new Map<string, Set<string>>();
    for (const edge of edges) {
      if (!map.has(edge.source_id)) map.set(edge.source_id, new Set());
      if (!map.has(edge.target_id)) map.set(edge.target_id, new Set());
      map.get(edge.source_id)!.add(edge.target_id);
      map.get(edge.target_id)!.add(edge.source_id);
      map.get(edge.source_id)!.add(edge.source_id);
      map.get(edge.target_id)!.add(edge.target_id);
    }
    return map;
  }, [edges]);

  const flowNodes: EntityFlowNode[] = useMemo(
    () =>
      nodes.map((node) => {
        const pos = layout.positions.get(node.id);
        return {
          id: node.id,
          type: "entity",
          position: { x: pos?.x ?? 0, y: pos?.y ?? 0 },
          data: {
            node,
            showMeta,
            state: buildFlowState(node, {
              selectedId,
              hoveredId,
              highlight,
              neighbours: hoveredId ? (neighbourMap.get(hoveredId) ?? new Set()) : new Set(),
            }),
          },
          style: { width: pos?.width ?? 190, height: pos?.height ?? 52 },
          draggable: true,
          connectable: false,
        } satisfies EntityFlowNode;
      }),
    [nodes, layout, showMeta, selectedId, hoveredId, highlight, neighbourMap],
  );

  const flowEdges: Edge[] = useMemo(
    () =>
      edges.map((edge) => {
        const meta = RELATIONSHIP_META[edge.relationship_type];
        const visual = entityVisual(
          nodes.find((n) => n.id === edge.flow_from)?.entity_type ?? "unknown",
        );
        const isFocusEdge = highlight ? highlight.edgeIds.has(edge.id) : null;
        const touchesHover =
          !highlight && hoveredId ? edge.source_id === hoveredId || edge.target_id === hoveredId : false;
        const touchesSelected =
          !highlight && selectedId
            ? edge.source_id === selectedId || edge.target_id === selectedId
            : false;

        let opacity = 0.42;
        let stroke = "#2e3947";
        let width = 1.15;
        if (highlight) {
          if (isFocusEdge) {
            opacity = 0.95;
            stroke = visual.color;
            width = 1.9;
          } else {
            opacity = 0.07;
          }
        } else if (touchesHover || touchesSelected) {
          opacity = 0.95;
          stroke = visual.color;
          width = 1.9;
        }

        return {
          id: edge.id,
          source: edge.flow_from,
          target: edge.flow_to,
          type: "smoothstep",
          animated: Boolean(highlight ? isFocusEdge : touchesHover),
          style: { stroke, strokeWidth: width, opacity },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: 13,
            height: 13,
            color: stroke,
          },
          label: meta.short,
          labelStyle: {
            fill: isFocusEdge || touchesHover ? "#c8d4e0" : "#6b7b8c",
            fontSize: 8.5,
            fontWeight: 600,
            fontFamily: "Inter, sans-serif",
          },
          labelBgStyle: { fill: "#0b0e13", fillOpacity: 0.88 },
          labelBgPadding: [3, 2] as [number, number],
          labelBgBorderRadius: 3,
          data: edge,
        } satisfies Edge;
      }),
    [edges, nodes, highlight, hoveredId, selectedId],
  );

  useEffect(() => {
    if (!fitSignal) return;
    const timer = window.setTimeout(() => {
      flow.fitView({ padding: 0.14, duration: 520, maxZoom: 1.05 });
    }, 40);
    return () => window.clearTimeout(timer);
  }, [fitSignal, flow]);

  useEffect(() => {
    if (!focusSignal) return;
    const pos = layout.positions.get(focusSignal.id);
    if (!pos) return;
    const timer = window.setTimeout(() => {
      flow.setCenter(pos.x + pos.width / 2, pos.y + pos.height / 2, {
        zoom: focusSignal.zoom ?? 0.92,
        duration: 480,
      });
    }, 30);
    return () => window.clearTimeout(timer);
  }, [focusSignal, layout, flow]);

  const onNodeClick: NodeMouseHandler = (_event, node) => {
    onSelect(node.id);
  };

  const onPaneClick = () => {
    onSelect(null);
    onHover(null);
  };

  const onEdgeClick: EdgeMouseHandler = (_event, edge) => {
    const data = edge.data as GraphEdge | undefined;
    if (data && onEdgeSelect) onEdgeSelect(data);
    else if (data) onSelect(data.flow_from);
  };

  return (
    <div ref={containerRef} className={cn("graph-backdrop h-full w-full", className)}>
      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        nodeTypes={{ entity: EntityNode }}
        onNodeClick={onNodeClick}
        onNodeMouseEnter={(_e, node) => onHover(node.id)}
        onNodeMouseLeave={() => onHover(null)}
        onPaneClick={onPaneClick}
        onEdgeClick={onEdgeClick}
        fitView
        fitViewOptions={{ padding: 0.14, maxZoom: 1.05 }}
        minZoom={0.12}
        maxZoom={1.9}
        nodesDraggable
        nodesConnectable={false}
        elementsSelectable
        panOnScroll
        zoomOnPinch
        zoomOnDoubleClick
        proOptions={{ hideAttribution: true }}
        defaultEdgeOptions={{ type: "smoothstep" }}
      >
        <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="#1b2430" />
        <Controls
          showInteractive={false}
          position="bottom-left"
          className="!bg-surface !border !border-line !rounded-[7px] !shadow-none overflow-hidden [&>button]:!bg-transparent [&>button]:!border-line [&>button]:!text-ink-muted hover:[&>button]:!bg-surface-2"
        />
        {showMinimap && (
          <MiniMap
            position="bottom-right"
            pannable
            zoomable
            maskColor="rgba(9,11,15,0.72)"
            nodeColor={(n) => {
              const data = (n.data as { node?: GraphNode })?.node;
              return data ? entityVisual(data.entity_type).color : "#334155";
            }}
            style={{ width: 168, height: 108 }}
          />
        )}
      </ReactFlow>
    </div>
  );
}

export function AtlasGraph(props: AtlasGraphProps) {
  return (
    <ReactFlowProvider>
      <AtlasGraphInner {...props} />
    </ReactFlowProvider>
  );
}

/** Compact colour/type legend used on the atlas canvas. */
export function GraphLegend({
  counts,
  activeTypes,
  onToggle,
  className,
}: {
  counts: Record<string, number>;
  activeTypes: Set<string>;
  onToggle: (type: string) => void;
  className?: string;
}) {
  const entries = Object.entries(counts)
    .filter(([type]) => type in entityVisual(type) || true)
    .sort((a, b) => b[1] - a[1]);

  return (
    <div className={cn("flex flex-wrap items-center gap-x-1 gap-y-1", className)}>
      {entries.map(([type, count]) => {
        const visual = entityVisual(type);
        const active = activeTypes.size === 0 || activeTypes.has(type);
        return (
          <button
            key={type}
            type="button"
            onClick={() => onToggle(type)}
            title={`${visual.label} · ${count} (click to filter)`}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-[4px] border px-1.5 py-[3px] text-[10.5px] transition-colors",
              active
                ? "border-line-strong bg-surface-2 text-ink-muted hover:text-ink"
                : "border-transparent bg-transparent text-subtle opacity-45 hover:opacity-80",
            )}
          >
            <span
              className="h-[6px] w-[6px] rounded-full"
              style={{ backgroundColor: visual.color }}
            />
            <span>{visual.label}</span>
            <span className="tabular text-subtle">{count}</span>
          </button>
        );
      })}
    </div>
  );
}

/** Edge-style legend explaining influence direction. */
export function FlowLegend({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center gap-3 text-[10.5px] text-subtle", className)}>
      <span className="inline-flex items-center gap-1.5">
        <svg width="26" height="8" aria-hidden>
          <defs>
            <marker id="lg-arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
              <path d="M0,0 L6,3 L0,6 z" fill="#6b7b8c" />
            </marker>
          </defs>
          <line x1="0" y1="4" x2="19" y2="4" stroke="#6b7b8c" strokeWidth="1.3" markerEnd="url(#lg-arrow)" />
        </svg>
        <span>Arrows show influence direction</span>
      </span>
      <span className="text-line-strong">|</span>
      <span>“read by” = the table is read by the script</span>
    </div>
  );
}

export function ConfidenceLegend({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      {(Object.keys(CONFIDENCE_META) as (keyof typeof CONFIDENCE_META)[]).map((key) => (
        <span key={key} className="inline-flex items-center gap-1 text-[10px] text-subtle">
          <span
            className="h-[5px] w-[5px] rounded-full"
            style={{ backgroundColor: CONFIDENCE_META[key].color }}
          />
          {CONFIDENCE_META[key].label}
        </span>
      ))}
    </div>
  );
}

export function GraphTooltipContent({
  node,
  className,
}: {
  node: GraphNode;
  className?: string;
}) {
  const visual = entityVisual(node.entity_type);
  return (
    <div className={cn("w-[248px] space-y-1.5", className)}>
      <div className="flex items-center gap-1.5">
        <span
          className="h-[6px] w-[6px] rounded-full"
          style={{ backgroundColor: visual.color }}
        />
        <span className="text-[9.5px] font-semibold uppercase tracking-[0.09em] text-subtle">
          {visual.label}
        </span>
      </div>
      <div className="text-[12px] font-semibold text-ink">{node.name}</div>
      {node.qualified_name && node.qualified_name !== node.name && (
        <div className="mono text-[10px] text-muted">{truncate(node.qualified_name, 48)}</div>
      )}
      <div className="flex items-center gap-2 pt-0.5 text-[10px] text-subtle">
        <span>{node.technology || "—"}</span>
        <span className="text-line-strong">·</span>
        <span>{node.owner || "unowned"}</span>
        <span className="text-line-strong">·</span>
        <span>{node.degree} links</span>
      </div>
    </div>
  );
}
