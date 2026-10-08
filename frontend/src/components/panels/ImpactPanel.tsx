import { useMemo, useState } from "react";
import {
  ArrowRight,
  ChevronDown,
  ChevronRight,
  Crosshair,
  Loader2,
  Radar,
  Route,
  X,
} from "lucide-react";
import type { Impact, PathResult, GraphNode } from "@/lib/types";
import { entityVisual, RELATIONSHIP_META, CONFIDENCE_META } from "@/lib/entity-visuals";
import { cn, formatNumber } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/misc";

/* ------------------------------------------------------------------ */
/* Impact summary                                                      */
/* ------------------------------------------------------------------ */
export function ImpactPanel({
  impact,
  loading,
  onClose,
  onSelectEntity,
  onChangeDirection,
  className,
}: {
  impact: Impact | null;
  loading: boolean;
  onClose: () => void;
  onSelectEntity: (id: string) => void;
  onChangeDirection: (direction: "downstream" | "upstream") => void;
  className?: string;
}) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const buckets = useMemo(() => {
    if (!impact) return [];
    return [
      { key: "integrations", label: "Integrations", value: impact.integrations },
      { key: "scripts", label: "Scripts", value: impact.scripts },
      { key: "jobs", label: "Scheduled jobs", value: impact.jobs },
      { key: "files", label: "Files", value: impact.files },
      { key: "external_services", label: "External services", value: impact.external_services },
      { key: "databases", label: "Database objects", value: impact.databases },
    ].filter((b) => b.value > 0);
  }, [impact]);

  if (!impact && !loading) return null;

  return (
    <section
      className={cn(
        "flex w-[340px] shrink-0 flex-col border-l border-line bg-surface",
        "slide-in-right",
        className,
      )}
    >
      <header className="flex items-start gap-2 border-b border-line px-4 pt-3.5 pb-3">
        <div className="flex-1">
          <div className="flex items-center gap-1.5">
            <Radar className="h-3.5 w-3.5 text-accent-strong" />
            <span className="text-[10px] font-semibold uppercase tracking-[0.09em] text-accent-strong">
              Impact analysis
            </span>
          </div>
          {impact ? (
            <>
              <h2 className="mt-1 truncate text-[14px] font-semibold leading-tight text-ink">
                {impact.root.name}
              </h2>
              <p className="mt-0.5 text-[11px] text-muted">
                Changing this may affect{" "}
                <span className="font-semibold text-ink">
                  {formatNumber(impact.total_affected)}
                </span>{" "}
                {impact.total_affected === 1 ? "entity" : "entities"}
              </p>
            </>
          ) : (
            <div className="mt-1 text-[12px] text-muted">Computing blast radius…</div>
          )}
        </div>
        <Button variant="ghost" size="iconSm" onClick={onClose} title="Close">
          <X className="h-3.5 w-3.5" />
        </Button>
      </header>

      {impact && (
        <div className="flex items-center gap-1 border-b border-line px-4 py-2">
          {(["downstream", "upstream"] as const).map((dir) => (
            <button
              key={dir}
              type="button"
              onClick={() => onChangeDirection(dir)}
              className={cn(
                "rounded-[4px] px-2 py-1 text-[10.5px] font-medium transition-colors",
                impact.direction === dir
                  ? "bg-accent-soft text-accent-strong"
                  : "text-subtle hover:bg-surface-2 hover:text-ink-muted",
              )}
            >
              {dir === "downstream" ? "What it affects" : "What affects it"}
            </button>
          ))}
          <span className="ml-auto text-[10px] text-subtle">
            {impact.max_depth ? `depth ≤ ${impact.max_depth}` : "full chain"}
          </span>
        </div>
      )}

      <div className="flex-1 overflow-y-auto px-4 py-3">
        {loading && (
          <div className="flex items-center gap-2 text-[12px] text-muted">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Traversing the graph…
          </div>
        )}

        {impact && !loading && (
          <>
            <div className="grid grid-cols-2 gap-1.5">
              {buckets.map((bucket) => (
                <div
                  key={bucket.key}
                  className="rounded-[6px] border border-line bg-surface-2 px-2.5 py-2"
                >
                  <div className="tabular text-[17px] font-semibold leading-tight text-ink">
                    {bucket.value}
                  </div>
                  <div className="text-[10px] uppercase tracking-[0.06em] text-subtle">
                    {bucket.label}
                  </div>
                </div>
              ))}
            </div>

            <Separator className="my-3.5" />

            <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-subtle">
              Affected entities
            </div>
            <div className="space-y-1">
              {impact.groups.map((group) => {
                const visual = entityVisual(group.entity_type);
                const open = expanded.has(group.entity_type);
                return (
                  <div key={group.entity_type} className="rounded-[6px] border border-line">
                    <button
                      type="button"
                      onClick={() =>
                        setExpanded((prev) => {
                          const next = new Set(prev);
                          if (next.has(group.entity_type)) next.delete(group.entity_type);
                          else next.add(group.entity_type);
                          return next;
                        })
                      }
                      className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left"
                    >
                      {open ? (
                        <ChevronDown className="h-3 w-3 text-subtle" />
                      ) : (
                        <ChevronRight className="h-3 w-3 text-subtle" />
                      )}
                      <span
                        className="h-[6px] w-[6px] rounded-full"
                        style={{ backgroundColor: visual.color }}
                      />
                      <span className="flex-1 text-[11.5px] text-ink">{group.label}</span>
                      <span className="tabular text-[10.5px] text-subtle">{group.count}</span>
                    </button>
                    {open && (
                      <div className="border-t border-line px-2 pb-1.5">
                        {group.entities.map((entity) => (
                          <button
                            key={entity.id}
                            type="button"
                            onClick={() => onSelectEntity(entity.id)}
                            className="flex w-full items-center gap-1.5 rounded-[4px] px-1.5 py-1 text-left hover:bg-surface-2"
                          >
                            <span className="min-w-0 flex-1 truncate text-[11px] text-muted hover:text-ink">
                              {entity.name}
                            </span>
                            <span className="text-[9px] text-subtle">
                              {CONFIDENCE_META[entity.confidence].label}
                            </span>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {impact.chains.length > 0 && (
              <>
                <Separator className="my-3.5" />
                <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-subtle">
                  Representative flows
                </div>
                <div className="space-y-1.5">
                  {impact.chains.slice(0, 6).map((chain, index) => (
                    <button
                      key={index}
                      type="button"
                      onClick={() => onSelectEntity(chain[chain.length - 1]?.entity.id ?? "")}
                      className="w-full rounded-[6px] border border-line bg-surface-2 px-2 py-1.5 text-left transition-colors hover:border-line-strong"
                    >
                      <div className="flex flex-wrap items-center gap-x-1 gap-y-0.5">
                        {chain.map((step, i) => {
                          const visual = entityVisual(step.entity.entity_type);
                          return (
                            <span key={`${step.entity.id}-${i}`} className="inline-flex items-center gap-1">
                              {i > 0 && (
                                <ArrowRight
                                  className="h-2.5 w-2.5 text-subtle"
                                  aria-label={
                                    step.relationship
                                      ? RELATIONSHIP_META[step.relationship.relationship_type].arrow
                                      : "to"
                                  }
                                />
                              )}
                              <span
                                className="text-[10px] text-ink-muted"
                                style={{ color: visual.color }}
                              >
                                {step.entity.name}
                              </span>
                            </span>
                          );
                        })}
                      </div>
                    </button>
                  ))}
                </div>
              </>
            )}
          </>
        )}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Path explorer                                                       */
/* ------------------------------------------------------------------ */
export function PathExplorer({
  result,
  loading,
  onClose,
  onSelectEntity,
  className,
}: {
  result: PathResult | null;
  loading: boolean;
  candidates: GraphNode[];
  onClose: () => void;
  onSelectEntity: (id: string) => void;
  className?: string;
}) {
  return (
    <section
      className={cn(
        "flex w-[320px] shrink-0 flex-col border-l border-line bg-surface",
        "slide-in-right",
        className,
      )}
    >
      <header className="flex items-center gap-2 border-b border-line px-4 pt-3.5 pb-3">
        <Route className="h-3.5 w-3.5 text-accent-strong" />
        <div className="flex-1">
          <div className="text-[10px] font-semibold uppercase tracking-[0.09em] text-accent-strong">
            Dependency path
          </div>
          {result && (
            <div className="mt-0.5 text-[11px] text-muted">
              {result.from_entity?.name} <ArrowRight className="inline h-2.5 w-2.5" />{" "}
              {result.to_entity?.name}
            </div>
          )}
        </div>
        <Button variant="ghost" size="iconSm" onClick={onClose}>
          <X className="h-3.5 w-3.5" />
        </Button>
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-3">
        {loading && (
          <div className="flex items-center gap-2 text-[12px] text-muted">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Searching for a path…
          </div>
        )}

        {!loading && result && !result.found && (
          <div className="rounded-[7px] border border-dashed border-line px-3 py-6 text-center">
            <Crosshair className="mx-auto h-5 w-5 text-subtle" />
            <div className="mt-2 text-[12px] font-medium text-ink">No path found</div>
            <p className="mt-1 text-[11px] leading-relaxed text-muted">
              These two entities are not connected in the current graph. Try widening the
              filters or confirming more relationships.
            </p>
          </div>
        )}

        {!loading && result?.found && (
          <div className="space-y-1">
            {result.steps.map((step, index) => {
              const visual = entityVisual(step.entity.entity_type);
              return (
                <div key={`${step.entity.id}-${index}`}>
                  {index > 0 && (
                    <div className="flex items-center gap-1.5 py-0.5 pl-3">
                      <div className="h-3 w-px" style={{ backgroundColor: visual.color }} />
                      <span className="text-[9.5px] text-subtle">
                        {step.relationship
                          ? RELATIONSHIP_META[step.relationship.relationship_type].arrow
                          : "related"}
                      </span>
                    </div>
                  )}
                  <button
                    type="button"
                    onClick={() => onSelectEntity(step.entity.id)}
                    className="flex w-full items-center gap-2 rounded-[6px] border border-transparent px-2 py-1.5 text-left transition-colors hover:border-line hover:bg-surface-2"
                  >
                    <span
                      className="h-[7px] w-[7px] shrink-0 rounded-full"
                      style={{ backgroundColor: visual.color }}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-[11.5px] text-ink">{step.entity.name}</div>
                      <div className="text-[9.5px] text-subtle">
                        {entityVisual(step.entity.entity_type).label}
                      </div>
                    </div>
                    <Badge variant="subtle" size="xs">
                      step {index + 1}
                    </Badge>
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}
