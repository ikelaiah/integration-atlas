"""Pydantic request/response models.

These are the public contract of the HTTP API and the CLI's JSON output.
They deliberately mirror :mod:`atlas.models` but stay decoupled so the
persistence layer can evolve without breaking clients.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from atlas.domain import (
    Confidence,
    EntityType,
    Environment,
    EvidenceKind,
    RelationshipType,
    ReviewStatus,
    RiskStatus,
    ScanStatus,
    Severity,
    SourceKind,
    SubjectKind,
)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=False)


# --------------------------------------------------------------------------- #
# Evidence
# --------------------------------------------------------------------------- #
class EvidenceOut(ORMModel):
    id: str
    subject_kind: SubjectKind
    evidence_kind: EvidenceKind
    source_path: str = ""
    line_start: int | None = None
    line_end: int | None = None
    snippet: str = ""
    parser: str = ""
    confidence: Confidence
    meta_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class EvidenceIn(BaseModel):
    evidence_kind: EvidenceKind = EvidenceKind.MANUAL_NOTE
    source_path: str = ""
    line_start: int | None = None
    line_end: int | None = None
    snippet: str = ""
    parser: str = "manual"
    confidence: Confidence = Confidence.MANUAL
    meta_json: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Entity
# --------------------------------------------------------------------------- #
class EntityOut(ORMModel):
    id: str
    workspace_id: str
    entity_type: EntityType
    name: str
    qualified_name: str = ""
    display_name: str = ""
    description: str = ""
    owner: str = ""
    environment: Environment
    location: str = ""
    technology: str = ""
    risk_level: Severity | None = None
    confidence: Confidence
    source_kind: SourceKind
    is_missing: bool = False
    meta_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class EntityCreate(BaseModel):
    entity_type: EntityType
    name: str
    qualified_name: str = ""
    description: str = ""
    owner: str = ""
    environment: Environment = Environment.UNKNOWN
    location: str = ""
    technology: str = ""
    confidence: Confidence = Confidence.MANUAL
    source_kind: SourceKind = SourceKind.MANUAL
    meta_json: dict[str, Any] = Field(default_factory=dict)


class EntityUpdate(BaseModel):
    name: str | None = None
    qualified_name: str | None = None
    description: str | None = None
    owner: str | None = None
    environment: Environment | None = None
    location: str | None = None
    technology: str | None = None
    risk_level: Severity | None = None
    confidence: Confidence | None = None
    meta_json: dict[str, Any] | None = None


# --------------------------------------------------------------------------- #
# Relationship
# --------------------------------------------------------------------------- #
class RelationshipOut(ORMModel):
    id: str
    workspace_id: str
    source_id: str
    target_id: str
    relationship_type: RelationshipType
    confidence: Confidence
    source_kind: SourceKind
    review_status: ReviewStatus
    label: str = ""
    meta_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class RelationshipCreate(BaseModel):
    source_id: str
    target_id: str
    relationship_type: RelationshipType
    label: str = ""
    confidence: Confidence = Confidence.MANUAL
    source_kind: SourceKind = SourceKind.MANUAL
    evidence: list[EvidenceIn] = Field(default_factory=list)
    meta_json: dict[str, Any] = Field(default_factory=dict)


class RelationshipUpdate(BaseModel):
    relationship_type: RelationshipType | None = None
    label: str | None = None
    confidence: Confidence | None = None
    review_status: ReviewStatus | None = None


class RelationshipDetail(RelationshipOut):
    source: EntityOut
    target: EntityOut
    evidence: list[EvidenceOut] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Graph
# --------------------------------------------------------------------------- #
class GraphNode(BaseModel):
    id: str
    entity_type: EntityType
    name: str
    qualified_name: str = ""
    display_name: str = ""
    technology: str = ""
    environment: Environment
    confidence: Confidence
    owner: str = ""
    risk_level: Severity | None = None
    is_missing: bool = False
    degree: int = 0
    meta_json: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    id: str
    source_id: str
    target_id: str
    relationship_type: RelationshipType
    #: Influence direction, already resolved from the flow map.
    flow_from: str
    flow_to: str
    confidence: Confidence
    review_status: ReviewStatus
    label: str = ""


class GraphOut(BaseModel):
    workspace_id: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    truncated: bool = False
    totals: dict[str, int] = Field(default_factory=dict)
    facets: dict[str, dict[str, int]] = Field(default_factory=dict)


class GraphQuery(BaseModel):
    entity_types: list[EntityType] = Field(default_factory=list)
    min_confidence: Confidence | None = None
    environments: list[Environment] = Field(default_factory=list)
    include_rejected: bool = False
    limit: int = 2000


# --------------------------------------------------------------------------- #
# Traversal / impact / path
# --------------------------------------------------------------------------- #
class StepOut(BaseModel):
    entity: GraphNode
    relationship: GraphEdge | None = None
    depth: int


class TraversalOut(BaseModel):
    root: GraphNode
    direction: str
    steps: list[StepOut]
    counts_by_type: dict[str, int] = Field(default_factory=dict)
    truncated: bool = False


class ImpactGroup(BaseModel):
    entity_type: EntityType
    label: str
    count: int
    entities: list[GraphNode]


class ImpactOut(BaseModel):
    root: GraphNode
    direction: str
    max_depth: int | None = None
    total_affected: int
    groups: list[ImpactGroup]
    integrations: int = 0
    scripts: int = 0
    jobs: int = 0
    files: int = 0
    external_services: int = 0
    databases: int = 0
    other: int = 0
    chains: list[list[StepOut]] = Field(default_factory=list)
    truncated: bool = False


class PathOut(BaseModel):
    found: bool
    mode: str = "none"
    from_entity: GraphNode | None = None
    to_entity: GraphNode | None = None
    steps: list[StepOut] = Field(default_factory=list)
    length: int = 0


# --------------------------------------------------------------------------- #
# Search
# --------------------------------------------------------------------------- #
class SearchHit(BaseModel):
    entity: GraphNode
    score: float
    matched_on: str


class SearchOut(BaseModel):
    query: str
    hits: list[SearchHit]
    total: int


# --------------------------------------------------------------------------- #
# Risk
# --------------------------------------------------------------------------- #
class RiskFindingOut(ORMModel):
    id: str
    workspace_id: str
    rule_id: str
    rule_name: str
    severity: Severity
    title: str
    reason: str = ""
    entity_id: str | None = None
    relationship_id: str | None = None
    status: RiskStatus
    details_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class RiskSummary(BaseModel):
    total: int
    by_severity: dict[str, int] = Field(default_factory=dict)
    findings: list[RiskFindingOut] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Workspace / overview
# --------------------------------------------------------------------------- #
class WorkspaceOut(ORMModel):
    id: str
    name: str
    slug: str
    description: str = ""
    is_demo: bool = False
    created_at: datetime
    updated_at: datetime


class WorkspaceCreate(BaseModel):
    name: str
    description: str = ""
    is_demo: bool = False


class OverviewOut(BaseModel):
    workspace: WorkspaceOut
    entity_counts: dict[str, int] = Field(default_factory=dict)
    relationship_counts: dict[str, int] = Field(default_factory=dict)
    totals: dict[str, int] = Field(default_factory=dict)
    confidence: dict[str, float] = Field(default_factory=dict)
    environments: dict[str, int] = Field(default_factory=dict)
    risk_summary: RiskSummary | None = None
    highlights: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Scans
# --------------------------------------------------------------------------- #
class ScanOut(ORMModel):
    id: str
    workspace_id: str
    root_path: str = ""
    status: ScanStatus
    scanner_summary: dict[str, Any] = Field(default_factory=dict)
    diff_summary: dict[str, Any] = Field(default_factory=dict)
    error: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ScanCreate(BaseModel):
    root_path: str
    workspace_id: str | None = None
    workspace_name: str | None = None
    apply_changes: bool = True


class ScanProgress(BaseModel):
    scan: ScanOut
    files_discovered: int = 0
    files_parsed: int = 0
    by_extension: dict[str, int] = Field(default_factory=dict)
    entities: int = 0
    relationships: int = 0
    secrets_redacted: int = 0
    warnings: int = 0
    events: list[str] = Field(default_factory=list)


class ScanPreview(BaseModel):
    scanner_summary: dict[str, Any]
    diff_summary: dict[str, Any]


class ScanCheckpointOut(BaseModel):
    scan_id: str
    root_path: str
    started_at: datetime | None
    finished_at: datetime | None
    before_counts: dict[str, int]
    after_counts: dict[str, int]


class HistoricalChange(BaseModel):
    kind: Literal["entity", "relationship"]
    action: Literal["added", "updated", "removed"]
    id: str
    name: str
    type: str
    changed_fields: list[str]
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    before_name: str | None
    after_name: str | None


class GraphComparisonOut(BaseModel):
    workspace_id: str
    from_scan_id: str
    from_phase: Literal["before", "after"]
    to_scan_id: str
    to_phase: Literal["before", "after"]
    from_counts: dict[str, int]
    to_counts: dict[str, int]
    counts: dict[str, dict[str, int]]
    total: int
    filtered_total: int
    changes: list[HistoricalChange]
    offset: int
    limit: int
    truncated: bool


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #
class ExportRequest(BaseModel):
    format: str = "json"
    include_evidence: bool = True
