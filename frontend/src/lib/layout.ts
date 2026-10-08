/**
 * Layered (Sugiyama-style) graph layout.
 *
 * Deliberately hand-rolled: ~150 lines, no dependency, and tuned for the
 * shape of integration graphs — a few wide layers, long chains, and node
 * sizes that vary by entity type.
 *
 * Coordinates are in React Flow space: x grows right, y grows down.
 */

import type { GraphEdge, GraphNode } from "./types";
import { entityVisual } from "./entity-visuals";

export interface LayoutOptions {
  nodeWidth?: number;
  nodeHeight?: number;
  layerGap?: number;
  rankGap?: number;
  padding?: number;
  direction?: "LR" | "TB";
}

const DEFAULTS: Required<LayoutOptions> = {
  nodeWidth: 190,
  nodeHeight: 52,
  layerGap: 108,
  rankGap: 30,
  padding: 40,
  direction: "LR",
};

export interface PositionedNode {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  layer: number;
}

export interface LayoutResult {
  positions: Map<string, PositionedNode>;
  width: number;
  height: number;
  layers: number;
}

export function layoutGraph(
  nodes: GraphNode[],
  edges: GraphEdge[],
  options: LayoutOptions = {},
): LayoutResult {
  const opts = { ...DEFAULTS, ...options };
  const positions = new Map<string, PositionedNode>();
  if (nodes.length === 0) {
    return { positions, width: 0, height: 0, layers: 0 };
  }

  const ids = new Set(nodes.map((n) => n.id));
  const sizeOf = (n: GraphNode) => {
    const scale = entityVisual(n.entity_type).scale;
    return {
      width: Math.round(opts.nodeWidth * (0.72 + scale * 0.28)),
      height: Math.round(opts.nodeHeight * (0.78 + scale * 0.22)),
    };
  };

  // Influence-direction adjacency, matching what the user sees as "flow".
  const out = new Map<string, string[]>();
  const indegree = new Map<string, number>();
  for (const id of ids) {
    out.set(id, []);
    indegree.set(id, 0);
  }
  for (const edge of edges) {
    if (!ids.has(edge.flow_from) || !ids.has(edge.flow_to)) continue;
    if (edge.flow_from === edge.flow_to) continue;
    out.get(edge.flow_from)!.push(edge.flow_to);
    indegree.set(edge.flow_to, (indegree.get(edge.flow_to) ?? 0) + 1);
  }

  // --- 1. layer assignment via longest path from sources ------------------
  const layer = new Map<string, number>();
  const queue = [...ids].filter((id) => (indegree.get(id) ?? 0) === 0);
  if (queue.length === 0) queue.push(nodes[0].id);
  const indegCopy = new Map(indegree);
  for (const id of queue) layer.set(id, 0);

  const topo: string[] = [];
  const work = [...queue];
  const seenTopo = new Set<string>();
  while (work.length) {
    const id = work.shift()!;
    if (seenTopo.has(id)) continue;
    seenTopo.add(id);
    topo.push(id);
    for (const next of out.get(id) ?? []) {
      layer.set(next, Math.max(layer.get(next) ?? 0, (layer.get(id) ?? 0) + 1));
      const remaining = (indegCopy.get(next) ?? 0) - 1;
      indegCopy.set(next, remaining);
      if (remaining <= 0) work.push(next);
    }
  }
  // Nodes in cycles never reach indegree 0; place them one layer after their
  // earliest predecessor so nothing is dropped.
  for (const node of nodes) {
    if (!layer.has(node.id)) {
      const preds = edges
        .filter((e) => e.flow_to === node.id && ids.has(e.flow_from))
        .map((e) => layer.get(e.flow_from) ?? 0);
      layer.set(node.id, preds.length ? Math.max(...preds) + 1 : 0);
      if (!seenTopo.has(node.id)) topo.push(node.id);
    }
  }

  // --- 2. grouping by layer ---------------------------------------------
  const maxLayer = Math.max(...[...layer.values()], 0);
  const layers: string[][] = Array.from({ length: maxLayer + 1 }, () => []);
  for (const node of nodes) {
    layers[layer.get(node.id) ?? 0].push(node.id);
  }

  // --- 3. crossing reduction (barycenter sweeps) -------------------------
  const indexInLayer = (id: string, l: number) => layers[l].indexOf(id);
  const neighboursTo = (id: string, l: number, forward: boolean) => {
    const targets: string[] = [];
    for (const edge of edges) {
      const from = forward ? edge.flow_from : edge.flow_to;
      const to = forward ? edge.flow_to : edge.flow_from;
      if (from === id && layer.get(to) === l) targets.push(to);
    }
    return targets;
  };

  for (let sweep = 0; sweep < 4; sweep++) {
    const forward = sweep % 2 === 0;
    const order = forward
      ? layers.map((_, i) => i).slice(1)
      : layers.map((_, i) => i).slice(0, -1).reverse();

    for (const l of order) {
      const reference = forward ? l - 1 : l + 1;
      layers[l].sort((a, b) => {
        const bary = (id: string) => {
          const refs = neighboursTo(id, reference, forward);
          if (refs.length === 0) return indexInLayer(id, l);
          return refs.reduce((sum, r) => sum + indexInLayer(r, reference), 0) / refs.length;
        };
        return bary(a) - bary(b);
      });
    }
  }

  // --- 4. coordinates ----------------------------------------------------
  // Row heights vary with the tallest node in the layer, so large system
  // nodes never overlap smaller table/column nodes.
  const sizes = new Map<string, { width: number; height: number }>();
  for (const node of nodes) sizes.set(node.id, sizeOf(node));

  const layerWidths = layers.map((idsInLayer) =>
    Math.max(0, ...idsInLayer.map((id) => sizes.get(id)!.width)),
  );
  const layerHeights = layers.map((idsInLayer) =>
    idsInLayer.reduce((sum, id) => sum + sizes.get(id)!.height, 0) +
    Math.max(0, idsInLayer.length - 1) * opts.rankGap,
  );

  const xOffsets: number[] = [];
  let cursorX = opts.padding;
  for (let l = 0; l < layers.length; l++) {
    xOffsets.push(cursorX);
    cursorX += layerWidths[l] + opts.layerGap;
  }
  const width = Math.max(cursorX - opts.layerGap + opts.padding, opts.padding * 2);

  const maxLayerHeight = Math.max(0, ...layerHeights);

  for (let l = 0; l < layers.length; l++) {
    let y = opts.padding + (maxLayerHeight - layerHeights[l]) / 2;
    for (const id of layers[l]) {
      const size = sizes.get(id)!;
      const x =
        xOffsets[l] + (layerWidths[l] - size.width) / 2;
      positions.set(id, {
        id,
        x: Math.round(opts.direction === "LR" ? x : y),
        y: Math.round(opts.direction === "LR" ? y : x),
        width: size.width,
        height: size.height,
        layer: l,
      });
      y += size.height + opts.rankGap;
    }
  }

  return {
    positions,
    width: Math.round(width),
    height: Math.round(maxLayerHeight + opts.padding * 2),
    layers: layers.length,
  };
}

/**
 * Radial-ish arrangement used for Focus Mode, so a node's neighbourhood is
 * readable at a glance rather than stretched across many layers.
 */
export function layoutNeighbourhood(
  rootId: string,
  nodes: GraphNode[],
  edges: GraphEdge[],
  options: { radius?: number; width?: number; height?: number } = {},
): Map<string, { x: number; y: number; width: number; height: number; layer: number }> {
  const radius = options.radius ?? 320;
  const positions = new Map<
    string,
    { x: number; y: number; width: number; height: number; layer: number }
  >();
  const others = nodes.filter((n) => n.id !== rootId);
  if (nodes.length === 0) return positions;

  const rootSize = { width: 200, height: 56 };
  positions.set(rootId, {
    x: 0,
    y: 0,
    width: rootSize.width,
    height: rootSize.height,
    layer: 0,
  });

  const degree = new Map<string, number>();
  for (const edge of edges) {
    degree.set(edge.source_id, (degree.get(edge.source_id) ?? 0) + 1);
    degree.set(edge.target_id, (degree.get(edge.target_id) ?? 0) + 1);
  }
  const sorted = [...others].sort(
    (a, b) => (degree.get(b.id) ?? 0) - (degree.get(a.id) ?? 0) || a.name.localeCompare(b.name),
  );

  sorted.forEach((node, i) => {
    const angle = (i / Math.max(sorted.length, 1)) * Math.PI * 2 - Math.PI / 2;
    const ring = i % 2 === 0 ? radius : radius * 1.45;
    const scale = entityVisual(node.entity_type).scale;
    positions.set(node.id, {
      x: Math.round(Math.cos(angle) * ring - 90),
      y: Math.round(Math.sin(angle) * ring - 26),
      width: Math.round(180 * (0.72 + scale * 0.28)),
      height: Math.round(52 * (0.78 + scale * 0.22)),
      layer: 1,
    });
  });

  return positions;
}
