import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  CornerDownLeft,
  LayoutDashboard,
  Loader2,
  Search,
  ShieldAlert,
  Waypoints,
} from "lucide-react";
import { api } from "@/lib/api";
import type { GraphNode } from "@/lib/types";
import { entityVisual, CONFIDENCE_META } from "@/lib/entity-visuals";
import { cn, truncate } from "@/lib/utils";
import { Kbd } from "@/components/ui/misc";

interface CommandItem {
  id: string;
  kind: "entity" | "action";
  title: string;
  subtitle: string;
  icon: React.ReactNode;
  accent?: string;
  run: () => void;
}

export function CommandPalette({
  open,
  onClose,
  workspaceId,
  onSelectEntity,
  onImpact,
}: {
  open: boolean;
  onClose: () => void;
  workspaceId: string | null;
  onSelectEntity: (id: string) => void;
  onImpact: (id: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<GraphNode[]>([]);
  const [loading, setLoading] = useState(false);
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!open) {
      setQuery("");
      setResults([]);
      setActive(0);
      return;
    }
    const timer = window.setTimeout(() => inputRef.current?.focus(), 20);
    return () => window.clearTimeout(timer);
  }, [open]);

  useEffect(() => {
    if (!open || !workspaceId || query.trim().length < 1) {
      setResults([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    const timer = window.setTimeout(() => {
      api
        .search(workspaceId, query, 24)
        .then((res) => {
          if (!cancelled) {
            setResults(res.hits.map((h) => h.entity));
            setActive(0);
          }
        })
        .catch(() => {
          if (!cancelled) setResults([]);
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, 130);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query, open, workspaceId]);

  const actions: CommandItem[] = useMemo(() => {
    const base: CommandItem[] = [
      {
        id: "action-overview",
        kind: "action",
        title: "Go to Overview",
        subtitle: "Estate summary and risk highlights",
        icon: <LayoutDashboard className="h-3.5 w-3.5" />,
        run: () => {
          navigate("/");
          onClose();
        },
      },
      {
        id: "action-atlas",
        kind: "action",
        title: "Go to Atlas",
        subtitle: "Open the integration graph",
        icon: <Waypoints className="h-3.5 w-3.5" />,
        run: () => {
          navigate("/atlas");
          onClose();
        },
      },
      {
        id: "action-risks",
        kind: "action",
        title: "Go to Risks",
        subtitle: "Explainable findings from the heuristic engine",
        icon: <ShieldAlert className="h-3.5 w-3.5" />,
        run: () => {
          navigate("/risks");
          onClose();
        },
      },
    ];
    return base;
  }, [navigate, onClose]);

  const items: CommandItem[] = useMemo(() => {
    const entityItems: CommandItem[] = results.map((node) => {
      const visual = entityVisual(node.entity_type);
      return {
        id: node.id,
        kind: "entity",
        title: node.name,
        subtitle: node.qualified_name || node.technology || visual.label,
        accent: visual.color,
        icon: (
          <span
            className="h-[7px] w-[7px] rounded-full"
            style={{ backgroundColor: visual.color }}
          />
        ),
        run: () => {
          onSelectEntity(node.id);
          navigate("/atlas");
          onClose();
        },
      };
    });

    const filteredActions = query.trim()
      ? actions.filter((a) => a.title.toLowerCase().includes(query.trim().toLowerCase()))
      : actions;

    return [...entityItems, ...filteredActions];
  }, [results, actions, query, onSelectEntity, navigate, onClose]);

  useEffect(() => {
    if (active >= items.length) setActive(Math.max(0, items.length - 1));
  }, [items.length, active]);

  if (!open) return null;

  const onKey = (event: React.KeyboardEvent) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((i) => (i + 1) % Math.max(items.length, 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((i) => (i - 1 + items.length) % Math.max(items.length, 1));
    } else if (event.key === "Enter") {
      event.preventDefault();
      const item = items[active];
      if (!item) return;
      // Shift+Enter runs impact analysis instead of just navigating.
      if (event.shiftKey && item.kind === "entity") {
        onImpact(item.id);
        onClose();
        return;
      }
      item.run();
    } else if (event.key === "Escape") {
      event.preventDefault();
      onClose();
    }
  };

  const grouped: Record<string, CommandItem[]> = {};
  for (const item of items) {
    const key = item.kind === "entity" ? "Entities" : "Actions";
    (grouped[key] ??= []).push(item);
  }

  let flatIndex = -1;

  return (
    <div
      className="fixed inset-0 z-[95] flex items-start justify-center bg-black/55 pt-[12vh] backdrop-blur-[2px]"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="w-full max-w-[560px] overflow-hidden rounded-[10px] border border-line-strong bg-surface float-shadow animate-[slide-up_160ms_cubic-bezier(0.22,1,0.36,1)]"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="Command palette"
      >
        <div className="flex items-center gap-2.5 border-b border-line px-3.5">
          <Search className="h-4 w-4 shrink-0 text-subtle" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKey}
            placeholder="Search students, tables, scripts, servers, APIs…"
            className="h-[46px] flex-1 bg-transparent text-[13.5px] text-ink placeholder:text-subtle focus:outline-none"
            spellCheck={false}
            autoComplete="off"
          />
          {loading && <Loader2 className="h-3.5 w-3.5 animate-spin text-subtle" />}
          <Kbd>ESC</Kbd>
        </div>

        <div className="max-h-[380px] overflow-y-auto py-1.5">
          {items.length === 0 && (
            <div className="px-4 py-8 text-center">
              <div className="text-[12px] text-muted">
                {query.trim() ? `No matches for “${query.trim()}”` : "Start typing to search the estate"}
              </div>
              <div className="mt-1 text-[11px] text-subtle">
                Try <span className="mono text-muted">Student</span>,{" "}
                <span className="mono text-muted">students.csv</span> or{" "}
                <span className="mono text-muted">APP-SERVER-01</span>
              </div>
            </div>
          )}

          {Object.entries(grouped).map(([group, groupItems]) => (
            <div key={group} className="mb-1">
              <div className="px-3.5 py-1 text-[9.5px] font-semibold uppercase tracking-[0.09em] text-subtle">
                {group}
              </div>
              {groupItems.map((item) => {
                flatIndex += 1;
                const isActive = flatIndex === active;
                const index = flatIndex;
                return (
                  <button
                    key={item.id}
                    type="button"
                    onMouseEnter={() => setActive(index)}
                    onClick={() => item.run()}
                    className={cn(
                      "flex w-full items-center gap-2.5 px-3.5 py-[7px] text-left transition-colors",
                      isActive ? "bg-surface-3" : "hover:bg-surface-2",
                    )}
                  >
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center">
                      {item.icon}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-[12.5px] text-ink">{item.title}</div>
                      <div className="truncate text-[10.5px] text-subtle">
                        {truncate(item.subtitle, 62)}
                      </div>
                    </div>
                    {item.kind === "entity" && (
                      <span
                        className="shrink-0 text-[9px] font-medium"
                        style={{
                          color: CONFIDENCE_META[
                            results.find((r) => r.id === item.id)?.confidence ?? "medium"
                          ]?.color,
                        }}
                      >
                        {entityVisual(results.find((r) => r.id === item.id)?.entity_type ?? "unknown").short}
                      </span>
                    )}
                    {isActive && (
                      <span className="flex shrink-0 items-center gap-1 text-[9.5px] text-subtle">
                        <CornerDownLeft className="h-2.5 w-2.5" />
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          ))}
        </div>

        <div className="flex items-center gap-3 border-t border-line bg-surface-2 px-3.5 py-2 text-[10px] text-subtle">
          <span className="flex items-center gap-1">
            <Kbd>↑</Kbd>
            <Kbd>↓</Kbd> navigate
          </span>
          <span className="flex items-center gap-1">
            <Kbd>↵</Kbd> open
          </span>
          <span className="flex items-center gap-1">
            <Kbd>⇧</Kbd>
            <Kbd>↵</Kbd> impact
          </span>
          <span className="flex items-center gap-1">
            <Kbd>esc</Kbd> close
          </span>
        </div>
      </div>
    </div>
  );
}
