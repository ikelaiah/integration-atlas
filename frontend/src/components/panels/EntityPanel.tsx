import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  ChevronRight,
  Copy,
  FileCode2,
  GitBranch,
  Lock,
  Radar,
  X,
} from "lucide-react";
import { api } from "@/lib/api";
import type { EntityDetail, RelationshipDetail, Severity } from "@/lib/types";
import {
  CONFIDENCE_META,
  entityVisual,
  RELATIONSHIP_META,
  SEVERITY_META,
} from "@/lib/entity-visuals";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { DetailRow } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { UnderlineTabs } from "@/components/ui/tabs";
import { Separator, Skeleton, EmptyState } from "@/components/ui/misc";

type Tab = "overview" | "dependencies" | "evidence" | "risks" | "metadata";

interface RiskFindingLite {
  id: string;
  rule_name: string;
  severity: Severity;
  title: string;
  reason: string;
  entity_id: string | null;
  details_json: Record<string, unknown>;
}

export interface EntityPanelProps {
  entityId: string | null;
  risks: RiskFindingLite[];
  onClose: () => void;
  onSelectEntity: (id: string) => void;
  onImpact: (id: string, direction: "downstream" | "upstream") => void;
  onFocus: (id: string) => void;
  className?: string;
}

export function EntityPanel({
  entityId,
  risks,
  onClose,
  onSelectEntity,
  onImpact,
  onFocus,
  className,
}: EntityPanelProps) {
  const [tab, setTab] = useState<Tab>("overview");
  const [entity, setEntity] = useState<EntityDetail | null>(null);
  const [relationships, setRelationships] = useState<RelationshipDetail[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!entityId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setTab("overview");
    Promise.all([api.entity(entityId), api.entityRelationships(entityId)])
      .then(([detail, rels]) => {
        if (cancelled) return;
        setEntity(detail);
        setRelationships(rels);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [entityId]);

  const entityRisks = useMemo(
    () => risks.filter((r) => r.entity_id === entityId),
    [risks, entityId],
  );

  const evidence = useMemo(
    () => relationships.flatMap((r) => r.evidence.map((e) => ({ evidence: e, relationship: r }))),
    [relationships],
  );

  if (!entityId) return null;

  return (
    <aside
      className={cn(
        "flex h-full w-[380px] shrink-0 flex-col border-l border-line bg-surface",
        "slide-in-right",
        className,
      )}
    >
      {/* header */}
      <div className="flex items-start gap-2 border-b border-line px-4 pt-3.5 pb-3">
        {loading ? (
          <div className="flex-1 space-y-2">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="h-5 w-48" />
          </div>
        ) : entity ? (
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <span
                className="h-[7px] w-[7px] shrink-0 rounded-full"
                style={{ backgroundColor: entityVisual(entity.entity_type).color }}
              />
              <span className="text-[10px] font-semibold uppercase tracking-[0.09em] text-subtle">
                {entityVisual(entity.entity_type).label}
              </span>
              {entity.is_missing && (
                <Badge variant="warning" size="xs">
                  <AlertTriangle className="h-2.5 w-2.5" /> not discovered
                </Badge>
              )}
            </div>
            <h2 className="mt-1 truncate text-[15px] font-semibold leading-tight tracking-tight text-ink">
              {entity.name}
            </h2>
            {entity.qualified_name && entity.qualified_name !== entity.name && (
              <div className="mono mt-0.5 truncate text-[10.5px] text-muted">
                {entity.qualified_name}
              </div>
            )}
          </div>
        ) : (
          <div className="flex-1 text-[12px] text-danger">{error ?? "Not found"}</div>
        )}
        <div className="flex items-center gap-1">
          {entity && (
            <Button
              variant="ghost"
              size="iconSm"
              title="Copy qualified name"
              onClick={() => navigator.clipboard?.writeText(entity.qualified_name || entity.name)}
            >
              <Copy className="h-3.5 w-3.5" />
            </Button>
          )}
          <Button variant="ghost" size="iconSm" title="Close (Esc)" onClick={onClose}>
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* quick actions */}
      {entity && (
        <div className="flex items-center gap-1.5 border-b border-line px-4 py-2.5">
          <Button size="xs" variant="subtle" onClick={() => onImpact(entity.id, "downstream")}>
            <Radar className="h-3 w-3" />
            Impact analysis
          </Button>
          <Button size="xs" variant="outline" onClick={() => onImpact(entity.id, "upstream")}>
            <ArrowUpRight className="h-3 w-3" />
            Upstream
          </Button>
          <Button size="xs" variant="outline" onClick={() => onFocus(entity.id)}>
            <GitBranch className="h-3 w-3" />
            Focus
          </Button>
        </div>
      )}

      <div className="px-3 pt-2">
        <UnderlineTabs
          value={tab}
          onChange={(v) => setTab(v as Tab)}
          tabs={[
            { value: "overview", label: "Overview" },
            { value: "dependencies", label: "Deps", count: relationships.length },
            { value: "evidence", label: "Evidence", count: evidence.length },
            { value: "risks", label: "Risks", count: entityRisks.length },
            { value: "metadata", label: "Meta" },
          ]}
        />
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3">
        {loading && (
          <div className="space-y-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
          </div>
        )}

        {!loading && entity && tab === "overview" && <OverviewTab entity={entity} />}
        {!loading && tab === "dependencies" && (
          <DependenciesTab
            relationships={relationships}
            entityId={entityId}
            onSelect={onSelectEntity}
          />
        )}
        {!loading && tab === "evidence" && <EvidenceTab items={evidence} />}
        {!loading && tab === "risks" && <RisksTab risks={entityRisks} />}
        {!loading && entity && tab === "metadata" && <MetadataTab entity={entity} />}
      </div>
    </aside>
  );
}

function OverviewTab({ entity }: { entity: EntityDetail }) {
  const visual = entityVisual(entity.entity_type);
  const confidence = CONFIDENCE_META[entity.confidence];
  return (
    <div className="space-y-1">
      {entity.description && (
        <p className="mb-3 text-[12px] leading-relaxed text-muted">{entity.description}</p>
      )}
      <DetailRow label="Type">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-[6px] w-[6px] rounded-full" style={{ backgroundColor: visual.color }} />
          {visual.label}
        </span>
      </DetailRow>
      {entity.technology && <DetailRow label="Technology">{entity.technology}</DetailRow>}
      {entity.location && (
        <DetailRow label="Location">
          <span className="mono break-all text-[11px] text-muted">{entity.location}</span>
        </DetailRow>
      )}
      <DetailRow label="Owner">{entity.owner || <span className="text-subtle">unowned</span>}</DetailRow>
      <DetailRow label="Environment">
        <Badge variant={entity.environment === "production" ? "accent" : "subtle"} size="xs">
          {entity.environment}
        </Badge>
      </DetailRow>
      <DetailRow label="Confidence">
        <Badge size="xs" dotColor={confidence.color}>
          {confidence.label}
        </Badge>
      </DetailRow>
      <DetailRow label="Source">
        <Badge variant={entity.source_kind === "manual" ? "accent" : "default"} size="xs">
          {entity.source_kind === "manual" ? (
            <>
              <Lock className="h-2.5 w-2.5" /> manual
            </>
          ) : (
            entity.source_kind
          )}
        </Badge>
      </DetailRow>
      {entity.risk_level && (
        <DetailRow label="Risk">
          <Badge size="xs" dotColor={SEVERITY_META[entity.risk_level].color}>
            {SEVERITY_META[entity.risk_level].label}
          </Badge>
        </DetailRow>
      )}
      {Object.keys(entity.meta_json ?? {}).length > 0 && (
        <>
          <Separator className="my-2.5" />
          {Object.entries(entity.meta_json)
            .slice(0, 10)
            .map(([key, value]) => (
              <DetailRow key={key} label={key}>
                <span className="mono break-all text-[11px] text-muted">
                  {typeof value === "object" ? JSON.stringify(value) : String(value)}
                </span>
              </DetailRow>
            ))}
        </>
      )}
    </div>
  );
}

function DependenciesTab({
  relationships,
  entityId,
  onSelect,
}: {
  relationships: RelationshipDetail[];
  entityId: string;
  onSelect: (id: string) => void;
}) {
  const outgoing = relationships.filter((r) => r.source_id === entityId);
  const incoming = relationships.filter((r) => r.target_id === entityId);

  if (relationships.length === 0) {
    return (
      <EmptyState
        title="No relationships yet"
        description="Run a scan or add a manual relationship to connect this entity to the estate."
      />
    );
  }

  return (
    <div className="space-y-4">
      {outgoing.length > 0 && (
        <RelationshipGroup title="Outgoing" rows={outgoing} entityId={entityId} onSelect={onSelect} />
      )}
      {incoming.length > 0 && (
        <RelationshipGroup title="Incoming" rows={incoming} entityId={entityId} onSelect={onSelect} />
      )}
    </div>
  );
}

function RelationshipGroup({
  title,
  rows,
  entityId,
  onSelect,
}: {
  title: string;
  rows: RelationshipDetail[];
  entityId: string;
  onSelect: (id: string) => void;
}) {
  return (
    <div>
      <div className="mb-1.5 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-subtle">
        {title === "Outgoing" ? (
          <ArrowDownRight className="h-3 w-3" />
        ) : (
          <ArrowUpRight className="h-3 w-3" />
        )}
        {title}
        <span className="tabular rounded-[3px] bg-surface-2 px-1 text-[9px]">{rows.length}</span>
      </div>
      <div className="space-y-1">
        {rows.map((rel) => {
          const other = rel.source_id === entityId ? rel.target : rel.source;
          const meta = RELATIONSHIP_META[rel.relationship_type];
          const otherVisual = entityVisual(other.entity_type);
          return (
            <button
              key={rel.id}
              type="button"
              onClick={() => onSelect(other.id)}
              className="group flex w-full items-center gap-2 rounded-[6px] border border-transparent px-2 py-1.5 text-left transition-colors hover:border-line hover:bg-surface-2"
            >
              <span
                className="h-[6px] w-[6px] shrink-0 rounded-full"
                style={{ backgroundColor: otherVisual.color }}
              />
              <div className="min-w-0 flex-1">
                <div className="truncate text-[11.5px] text-ink">{other.name}</div>
                <div className="flex items-center gap-1.5">
                  <span className="text-[9.5px] text-subtle">{meta.label}</span>
                  <span className="text-line-strong">·</span>
                  <span
                    className="text-[9.5px]"
                    style={{ color: CONFIDENCE_META[rel.confidence].color }}
                  >
                    {CONFIDENCE_META[rel.confidence].label}
                  </span>
                </div>
              </div>
              <ChevronRight className="h-3 w-3 shrink-0 text-subtle opacity-0 transition-opacity group-hover:opacity-100" />
            </button>
          );
        })}
      </div>
    </div>
  );
}

function EvidenceTab({
  items,
}: {
  items: { evidence: RelationshipDetail["evidence"][number]; relationship: RelationshipDetail }[];
}) {
  if (items.length === 0) {
    return (
      <EmptyState
        icon={<FileCode2 className="h-5 w-5" />}
        title="No evidence recorded"
        description="Discovered relationships carry the exact file, line and snippet that produced them."
      />
    );
  }

  return (
    <div className="space-y-2.5">
      {items.map(({ evidence, relationship }) => (
        <div
          key={evidence.id}
          className="rounded-[7px] border border-line bg-surface-2 overflow-hidden"
        >
          <div className="flex items-center gap-1.5 border-b border-line px-2.5 py-1.5">
            <Badge variant="subtle" size="xs">
              {evidence.evidence_kind.replace(/_/g, " ")}
            </Badge>
            <Badge size="xs" dotColor={CONFIDENCE_META[evidence.confidence].color}>
              {CONFIDENCE_META[evidence.confidence].label}
            </Badge>
            <span className="ml-auto truncate text-[9.5px] text-subtle">
              {relationship.source.name} → {relationship.target.name}
            </span>
          </div>
          {evidence.source_path && (
            <div className="flex items-center gap-1.5 px-2.5 pt-2 text-[10px] text-muted">
              <FileCode2 className="h-3 w-3 shrink-0 text-subtle" />
              <span className="mono truncate">{evidence.source_path}</span>
              {evidence.line_start != null && (
                <span className="mono shrink-0 text-subtle">:{evidence.line_start}</span>
              )}
            </div>
          )}
          {evidence.snippet && (
            <pre className="mono m-2 rounded-[4px] border border-line bg-canvas px-2.5 py-2 text-[10px] leading-[1.55] text-ink-muted overflow-x-auto whitespace-pre-wrap break-words">
              {evidence.snippet}
            </pre>
          )}
          {evidence.parser && (
            <div className="px-2.5 pb-2 text-[9.5px] text-subtle">
              detected by <span className="mono">{evidence.parser}</span>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function RisksTab({ risks }: { risks: RiskFindingLite[] }) {
  if (risks.length === 0) {
    return (
      <EmptyState
        icon={<AlertTriangle className="h-5 w-5" />}
        title="No open risks"
        description="The heuristic risk engine found nothing to flag for this entity."
      />
    );
  }
  return (
    <div className="space-y-2">
      {risks.map((risk) => (
        <div key={risk.id} className="rounded-[7px] border border-line bg-surface-2 p-2.5">
          <div className="flex items-start gap-2">
            <span
              className="mt-[5px] h-[6px] w-[6px] shrink-0 rounded-full"
              style={{ backgroundColor: SEVERITY_META[risk.severity].color }}
            />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5">
                <Badge size="xs" dotColor={SEVERITY_META[risk.severity].color}>
                  {SEVERITY_META[risk.severity].label}
                </Badge>
                <span className="truncate text-[10px] text-subtle">{risk.rule_name}</span>
              </div>
              <div className="mt-1 text-[11.5px] font-medium leading-snug text-ink">
                {risk.title}
              </div>
              {risk.reason && (
                <p className="mt-1 text-[11px] leading-relaxed text-muted">{risk.reason}</p>
              )}
              {Object.keys(risk.details_json ?? {}).length > 0 && (
                <div className="mono mt-1.5 rounded-[4px] border border-line bg-canvas px-2 py-1.5 text-[9.5px] text-subtle">
                  {Object.entries(risk.details_json)
                    .map(([k, v]) => `${k}=${Array.isArray(v) ? v.join(", ") : String(v)}`)
                    .join("  ")}
                </div>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function MetadataTab({ entity }: { entity: EntityDetail }) {
  return (
    <div className="space-y-1">
      <DetailRow label="ID">
        <span className="mono text-[10.5px] text-muted">{entity.id}</span>
      </DetailRow>
      <DetailRow label="Workspace">
        <span className="mono text-[10.5px] text-muted">{entity.workspace_id}</span>
      </DetailRow>
      <DetailRow label="Qualified">
        <span className="mono break-all text-[10.5px] text-muted">{entity.qualified_name}</span>
      </DetailRow>
      <DetailRow label="Created">
        <span className="text-[11px] text-muted">{entity.created_at}</span>
      </DetailRow>
      <DetailRow label="Updated">
        <span className="text-[11px] text-muted">{entity.updated_at}</span>
      </DetailRow>
      <Separator className="my-2.5" />
      <pre className="mono rounded-[5px] border border-line bg-canvas px-2.5 py-2 text-[9.5px] leading-relaxed text-subtle overflow-x-auto">
        {JSON.stringify(entity.meta_json ?? {}, null, 2)}
      </pre>
    </div>
  );
}
