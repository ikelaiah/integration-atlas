import { memo } from "react";
import { Handle, Position, type NodeProps, type Node } from "@xyflow/react";
import { AlertTriangle, Lock, Sparkles } from "lucide-react";
import type { GraphNode } from "@/lib/types";
import { entityVisual, CONFIDENCE_META } from "@/lib/entity-visuals";
import { cn, truncate } from "@/lib/utils";

export interface EntityNodeData extends Record<string, unknown> {
  node: GraphNode;
  state: "default" | "selected" | "highlight" | "dimmed" | "impact" | "path" | "root";
  showMeta: boolean;
}

export type EntityFlowNode = Node<EntityNodeData, "entity">;

function NodeShell({
  data,
  selected,
}: {
  data: EntityNodeData;
  selected: boolean;
}) {
  const { node, state, showMeta } = data;
  const visual = entityVisual(node.entity_type);
  const confidence = CONFIDENCE_META[node.confidence];

  const isDim = state === "dimmed";
  const isImpact = state === "impact";
  const isPath = state === "path";
  const isRoot = state === "root";
  const isHighlight = state === "highlight";

  return (
    <div
      className={cn(
        "group relative h-full w-full select-none transition-all duration-200",
        isDim && "opacity-[0.18] saturate-[0.3]",
      )}
      style={
        {
          "--node-color": visual.color,
        } as React.CSSProperties
      }
    >
      <Handle type="target" position={Position.Left} className="!opacity-0" />
      <Handle type="source" position={Position.Right} className="!opacity-0" />

      <div
        className={cn(
          "relative flex h-full w-full flex-col justify-center overflow-hidden rounded-[7px] border bg-surface-2",
          "transition-[box-shadow,border-color,transform] duration-200",
          isImpact && "border-[var(--node-color)] shadow-[0_0_0_1px_var(--node-color),0_0_22px_-2px_var(--node-color)]",
          isPath && "border-[var(--node-color)] shadow-[0_0_0_1.5px_var(--node-color),0_0_26px_-2px_var(--node-color)]",
          isRoot && "border-[var(--node-color)] shadow-[0_0_0_2px_var(--node-color),0_0_30px_-2px_var(--node-color)]",
          isHighlight && "border-[color-mix(in_srgb,var(--node-color)_55%,transparent)]",
          selected &&
            !isImpact &&
            !isRoot &&
            !isPath &&
            "border-[var(--node-color)] shadow-[0_0_0_1px_var(--node-color),0_10px_28px_-12px_rgba(0,0,0,0.7)]",
          !selected && !isImpact && !isRoot && !isPath && !isHighlight && "border-line-strong hover:border-[#3d4a5a]",
        )}
      >
        {/* Colour spine */}
        <div
          className="absolute left-0 top-0 h-full w-[3px]"
          style={{
            background: `linear-gradient(180deg, var(--node-color), color-mix(in srgb, var(--node-color) 45%, transparent))`,
          }}
        />

        <div className="flex min-w-0 flex-1 flex-col justify-center gap-[3px] pl-3 pr-2.5 py-1.5">
          <div className="flex items-center gap-1.5">
            <span
              className="h-[6px] w-[6px] shrink-0 rounded-full"
              style={{ backgroundColor: "var(--node-color)" }}
              aria-hidden
            />
            <span className="text-[9.5px] font-semibold uppercase tracking-[0.09em] text-subtle">
              {visual.short}
            </span>
            {node.is_missing && (
              <AlertTriangle className="h-3 w-3 shrink-0 text-warning" aria-label="Not discovered" />
            )}
            {node.source_kind === "manual" && (
              <Lock className="h-2.5 w-2.5 shrink-0 text-subtle" aria-label="Manual" />
            )}
            {(isImpact || isPath || isRoot) && (
              <Sparkles className="h-3 w-3 shrink-0" style={{ color: "var(--node-color)" }} />
            )}
          </div>

          <div
            className="truncate text-[12px] font-medium leading-tight text-ink"
            title={node.display_name || node.name}
          >
            {truncate(node.name, 30)}
          </div>

          {showMeta && (
            <div className="flex items-center gap-1.5">
              {node.technology && (
                <span className="truncate text-[9.5px] text-subtle">{node.technology}</span>
              )}
              {node.confidence !== "medium" && (
                <span
                  className="ml-auto shrink-0 text-[9px] font-medium"
                  style={{ color: confidence.color }}
                  title={`Confidence: ${confidence.label}`}
                >
                  {confidence.label}
                </span>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export const EntityNode = memo(function EntityNode(props: NodeProps<EntityFlowNode>) {
  return <NodeShell data={props.data} selected={props.selected} />;
});
