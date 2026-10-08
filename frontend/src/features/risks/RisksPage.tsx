import { useMemo, useState } from "react";
import { Loader2, ShieldCheck } from "lucide-react";
import type { RiskFinding, Severity } from "@/lib/types";
import { SEVERITY_META } from "@/lib/entity-visuals";
import { formatNumber } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState, Stat } from "@/components/ui/misc";

const SEVERITY_ORDER: Severity[] = ["critical", "high", "medium", "low", "info"];

export function RisksPage({
  risks,
  loading,
  onSelect,
}: {
  risks: RiskFinding[];
  loading: boolean;
  onSelect: (id: string) => void;
}) {
  const [filter, setFilter] = useState<Severity | "all">("all");

  const counts = useMemo(() => {
    const map: Record<string, number> = {};
    for (const risk of risks) map[risk.severity] = (map[risk.severity] ?? 0) + 1;
    return map;
  }, [risks]);

  const visible = useMemo(
    () =>
      filter === "all"
        ? risks
        : risks.filter((r) => r.severity === filter),
    [risks, filter],
  );

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-[1180px] px-6 py-7">
        <div>
          <h1 className="text-[21px] font-semibold leading-tight tracking-tight text-ink">
            Risk findings
          </h1>
          <p className="mt-1 max-w-[680px] text-[12px] leading-relaxed text-muted">
            Every finding is explainable: a named heuristic rule, the reason it fired, and the
            artefacts it pointed at. No opaque scores.
          </p>
        </div>

        <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-5">
          {SEVERITY_ORDER.map((severity) => (
            <Stat
              key={severity}
              label={SEVERITY_META[severity].label}
              value={formatNumber(counts[severity] ?? 0)}
              accent={SEVERITY_META[severity].color}
              onClick={() => setFilter(filter === severity ? "all" : severity)}
            />
          ))}
        </div>

        <div className="mt-5 flex items-center gap-1.5">
          <Button
            variant={filter === "all" ? "subtle" : "ghost"}
            size="xs"
            onClick={() => setFilter("all")}
          >
            All
          </Button>
          {SEVERITY_ORDER.filter((s) => (counts[s] ?? 0) > 0).map((severity) => (
            <Button
              key={severity}
              variant={filter === severity ? "subtle" : "ghost"}
              size="xs"
              onClick={() => setFilter(severity)}
            >
              <span
                className="h-[5px] w-[5px] rounded-full"
                style={{ backgroundColor: SEVERITY_META[severity].color }}
              />
              {SEVERITY_META[severity].label}
              <span className="tabular opacity-70">{counts[severity]}</span>
            </Button>
          ))}
          <span className="ml-auto text-[10.5px] text-subtle">
            {formatNumber(visible.length)} shown
          </span>
        </div>

        <div className="mt-3 space-y-2">
          {loading && (
            <div className="flex items-center gap-2 py-8 text-[12px] text-muted">
              <Loader2 className="h-4 w-4 animate-spin" /> Running the heuristic rules…
            </div>
          )}

          {!loading && visible.length === 0 && (
            <EmptyState
              icon={<ShieldCheck className="h-6 w-6" />}
              title="No findings"
              description="The risk engine found nothing to flag under this filter."
            />
          )}

          {!loading &&
            visible.map((risk) => {
              const meta = SEVERITY_META[risk.severity];
              return (
                <div
                  key={risk.id}
                  className="rounded-[9px] border border-line bg-surface p-3.5 transition-colors hover:border-line-strong"
                >
                  <div className="flex items-start gap-2.5">
                    <span
                      className="mt-[5px] h-[7px] w-[7px] shrink-0 rounded-full"
                      style={{ backgroundColor: meta.color }}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Badge size="xs" dotColor={meta.color}>
                          {meta.label}
                        </Badge>
                        <Badge variant="subtle" size="xs">
                          {risk.rule_name}
                        </Badge>
                        <span className="mono text-[9.5px] text-subtle">{risk.rule_id}</span>
                      </div>
                      <h3 className="mt-1.5 text-[13px] font-medium leading-snug text-ink">
                        {risk.title}
                      </h3>
                      {risk.reason && (
                        <p className="mt-1 max-w-[820px] text-[11.5px] leading-relaxed text-muted">
                          {risk.reason}
                        </p>
                      )}
                      {Object.keys(risk.details_json ?? {}).length > 0 && (
                        <div className="mono mt-2 flex flex-wrap gap-1.5">
                          {Object.entries(risk.details_json).map(([key, value]) => (
                            <span
                              key={key}
                              className="rounded-[4px] border border-line bg-surface-2 px-1.5 py-[2px] text-[9.5px] text-subtle"
                            >
                              {key}:{" "}
                              <span className="text-muted">
                                {Array.isArray(value) ? value.join(", ") : String(value)}
                              </span>
                            </span>
                          ))}
                        </div>
                      )}
                      {risk.entity_id && (
                        <div className="mt-2">
                          <Button variant="outline" size="xs" onClick={() => onSelect(risk.entity_id!)}>
                            Inspect on the Atlas
                          </Button>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
        </div>
      </div>
    </div>
  );
}
