import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Radar,
  ShieldAlert,
  Waypoints,
} from "lucide-react";
import { api } from "@/lib/api";
import type { Overview } from "@/lib/types";
import { CONFIDENCE_META, entityVisual } from "@/lib/entity-visuals";
import { formatNumber } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Stat, Skeleton, EmptyState, Separator } from "@/components/ui/misc";

export function OverviewPage({ workspaceId }: { workspaceId: string | null }) {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    if (!workspaceId) return;
    setLoading(true);
    api.workspaces
      .overview(workspaceId)
      .then(setOverview)
      .catch(() => setOverview(null))
      .finally(() => setLoading(false));
  }, [workspaceId]);

  const topEntityTypes = useMemo(() => {
    if (!overview) return [];
    return Object.entries(overview.entity_counts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10);
  }, [overview]);

  const topRelationshipTypes = useMemo(() => {
    if (!overview) return [];
    return Object.entries(overview.relationship_counts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8);
  }, [overview]);

  if (loading) {
    return (
      <div className="h-full overflow-y-auto p-6">
        <div className="mx-auto max-w-[1180px] space-y-4">
          <Skeleton className="h-8 w-[320px]" />
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-[86px]" />
            ))}
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <Skeleton className="h-[220px]" />
            <Skeleton className="h-[220px]" />
            <Skeleton className="h-[220px]" />
          </div>
        </div>
      </div>
    );
  }

  if (!overview) {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <EmptyState
          title="No workspace loaded"
          description="Load the Northstar demo estate to see the integration overview."
          action={
            <Button variant="default" size="sm" onClick={() => api.workspaces.seedDemo().then(() => window.location.reload())}>
              Load demo estate
            </Button>
          }
        />
      </div>
    );
  }

  const confEntries = Object.entries(overview.confidence).sort(
    (a, b) => CONFIDENCE_META[a[0] as keyof typeof CONFIDENCE_META].rank -
              CONFIDENCE_META[b[0] as keyof typeof CONFIDENCE_META].rank,
  );

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-[1180px] px-6 py-7">
        {/* headline */}
        <div className="flex items-start justify-between gap-6">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-[24px] font-semibold leading-tight tracking-tight text-ink">
                Integration Estate
              </h1>
              {overview.workspace.is_demo && (
                <Badge variant="accent" size="sm">
                  demo
                </Badge>
              )}
            </div>
            <p className="mt-1.5 max-w-[620px] text-[12.5px] leading-relaxed text-muted">
              {overview.workspace.name} ·{" "}
              {overview.workspace.description || "Discovered from local artefacts."}
            </p>
          </div>
          <Button variant="default" size="md" onClick={() => navigate("/atlas")}>
            <Waypoints className="h-3.5 w-3.5" />
            Open Atlas
          </Button>
        </div>

        {/* key numbers */}
        <div className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
          <Stat
            label="Systems"
            value={formatNumber(overview.totals.systems ?? 0)}
            hint="business systems"
            accent={entityVisual("system").color}
          />
          <Stat
            label="Integrations"
            value={formatNumber(overview.entity_counts.integration ?? 0)}
            hint="named flows"
            accent={entityVisual("integration").color}
          />
          <Stat
            label="Scheduled jobs"
            value={formatNumber(overview.totals.jobs ?? 0)}
            hint="cron + task scheduler"
            accent={entityVisual("scheduled_job").color}
          />
          <Stat
            label="Databases"
            value={formatNumber(overview.totals.databases ?? 0)}
            hint="schemas + tables + columns"
            accent={entityVisual("database").color}
          />
          <Stat
            label="Scripts"
            value={formatNumber(overview.totals.scripts ?? 0)}
            hint="python · powershell · sql"
            accent={entityVisual("script").color}
          />
          <Stat
            label="External services"
            value={formatNumber(overview.totals.external_services ?? 0)}
            hint="SaaS + APIs"
            accent={entityVisual("external_service").color}
          />
        </div>

        <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
          {/* confidence */}
          <Card>
            <CardHeader>
              <CardTitle>Discovery confidence</CardTitle>
              <p className="mt-0.5 text-[11px] text-subtle">
                How sure Atlas is about each discovered item
              </p>
            </CardHeader>
            <CardContent>
              <div className="space-y-2.5">
                {confEntries.map(([key, pct]) => {
                  const meta = CONFIDENCE_META[key as keyof typeof CONFIDENCE_META];
                  return (
                    <div key={key}>
                      <div className="flex items-baseline justify-between">
                        <span className="flex items-center gap-1.5 text-[11.5px] text-ink">
                          <span
                            className="h-[6px] w-[6px] rounded-full"
                            style={{ backgroundColor: meta.color }}
                          />
                          {meta.label}
                        </span>
                        <span className="tabular text-[11.5px] text-muted">{pct}%</span>
                      </div>
                      <div className="mt-1 h-[5px] w-full overflow-hidden rounded-full bg-surface-2">
                        <div
                          className="h-full rounded-full transition-[width] duration-700"
                          style={{ width: `${pct}%`, backgroundColor: meta.color }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>

          {/* highlights / risks */}
          <Card>
            <CardHeader>
              <div className="flex items-center gap-1.5">
                <ShieldAlert className="h-3.5 w-3.5 text-warning" />
                <CardTitle>Potential risks</CardTitle>
              </div>
              <p className="mt-0.5 text-[11px] text-subtle">
                Explainable findings from the heuristic engine
              </p>
            </CardHeader>
            <CardContent>
              <div className="space-y-1.5">
                {overview.highlights.length === 0 && (
                  <div className="rounded-[6px] border border-dashed border-line px-3 py-5 text-center text-[11.5px] text-subtle">
                    Nothing flagged in this workspace.
                  </div>
                )}
                {overview.highlights.map((line, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => navigate("/risks")}
                    className="flex w-full items-start gap-2 rounded-[6px] border border-transparent px-2 py-1.5 text-left transition-colors hover:border-line hover:bg-surface-2"
                  >
                    <AlertTriangle className="mt-[2px] h-3 w-3 shrink-0 text-warning" />
                    <span className="flex-1 text-[11.5px] leading-relaxed text-ink">{line}</span>
                    <ArrowRight className="h-3 w-3 shrink-0 text-subtle opacity-0 transition-opacity group-hover:opacity-100" />
                  </button>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* composition */}
          <Card>
            <CardHeader>
              <CardTitle>Estate composition</CardTitle>
              <p className="mt-0.5 text-[11px] text-subtle">
                {formatNumber(overview.totals.entities ?? 0)} entities ·{" "}
                {formatNumber(overview.totals.relationships ?? 0)} relationships
              </p>
            </CardHeader>
            <CardContent>
              <div className="space-y-1.5">
                {topEntityTypes.map(([type, count]) => {
                  const visual = entityVisual(type);
                  const pct = ((count / (overview.totals.entities ?? 1)) * 100).toFixed(1);
                  return (
                    <button
                      key={type}
                      type="button"
                      onClick={() => navigate("/systems")}
                      className="flex w-full items-center gap-2 rounded-[5px] px-1.5 py-[3px] text-left hover:bg-surface-2"
                    >
                      <span
                        className="h-[6px] w-[6px] shrink-0 rounded-full"
                        style={{ backgroundColor: visual.color }}
                      />
                      <span className="flex-1 truncate text-[11px] text-ink-muted">
                        {visual.label}
                      </span>
                      <span className="tabular text-[11px] text-muted">{count}</span>
                      <span className="tabular w-[38px] text-right text-[9.5px] text-subtle">
                        {pct}%
                      </span>
                    </button>
                  );
                })}
              </div>
              <Separator className="my-3" />
              <div className="space-y-1">
                {topRelationshipTypes.map(([type, count]) => (
                  <div key={type} className="flex items-center gap-2 px-1.5 py-[2px]">
                    <span className="w-[78px] truncate text-[10px] text-subtle">
                      {type.replace(/_/g, " ")}
                    </span>
                    <div className="h-[4px] flex-1 overflow-hidden rounded-full bg-surface-2">
                      <div
                        className="h-full rounded-full bg-accent/60"
                        style={{
                          width: `${Math.min(100, (count / (overview.relationship_counts[Object.keys(overview.relationship_counts)[0]] ?? 1)) * 100)}%`,
                        }}
                      />
                    </div>
                    <span className="tabular w-[28px] text-right text-[10px] text-muted">{count}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* environments + quick links */}
        <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
          <Card>
            <CardHeader>
              <CardTitle>Environments</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(overview.environments).map(([env, count]) => (
                  <Badge
                    key={env}
                    variant={env === "production" ? "accent" : "subtle"}
                    size="md"
                  >
                    {env} <span className="tabular opacity-70">{count}</span>
                  </Badge>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Start here</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-1">
                {[
                  { icon: Radar, label: "Impact analysis on StudentID", to: "/atlas" },
                  { icon: Waypoints, label: "Explore the integration graph", to: "/atlas" },
                  { icon: ShieldAlert, label: "Review open risks", to: "/risks" },
                  { icon: Activity, label: "See named integrations", to: "/integrations" },
                ].map((item) => (
                  <button
                    key={item.label}
                    type="button"
                    onClick={() => navigate(item.to)}
                    className="flex w-full items-center gap-2 rounded-[5px] px-2 py-1.5 text-left hover:bg-surface-2"
                  >
                    <item.icon className="h-3.5 w-3.5 text-subtle" />
                    <span className="flex-1 text-[11.5px] text-ink-muted">{item.label}</span>
                    <ArrowRight className="h-3 w-3 text-subtle" />
                  </button>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Relationship vocabulary</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-1">
                {[
                  "reads_from",
                  "writes_to",
                  "calls",
                  "runs",
                  "produces",
                  "consumes",
                  "depends_on",
                  "uses_column",
                  "exports_to",
                  "triggers",
                ].map((rel) => (
                  <span
                    key={rel}
                    className="rounded-[4px] border border-line bg-surface-2 px-1.5 py-[2px] text-[10px] text-ink-muted"
                  >
                    {rel}
                  </span>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
