"""SQLAlchemy ORM models.

Dialect-neutral by design: the default is SQLite, but nothing here assumes it.
Identifiers are text UUIDs so rows can be merged across workspaces and exported
without integer-collision headaches.

``metadata`` is a reserved SQLAlchemy attribute, so the JSON payload columns
are named ``meta_json`` / ``details_json``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

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


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[str]: JSON}


class Workspace(Base):
    """A user-visible project or scope, e.g. "Student Systems"."""

    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    entities: Mapped[list[Entity]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )


class Entity(Base):
    """A node in the integration graph."""

    __tablename__ = "entities"
    __table_args__ = (
        UniqueConstraint("workspace_id", "fingerprint", name="uq_entity_fingerprint"),
        Index("ix_entities_workspace_type", "workspace_id", "entity_type"),
        Index("ix_entities_workspace_name", "workspace_id", "name"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    #: Dotted/hierarchical identity, e.g. ``LegacySIS.Student.StudentID``.
    qualified_name: Mapped[str] = mapped_column(String(600), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    owner: Mapped[str] = mapped_column(String(200), default="")
    environment: Mapped[str] = mapped_column(
        String(20), default=Environment.UNKNOWN.value, nullable=False
    )
    #: Path, URL, host:port or other locator. Never a secret.
    location: Mapped[str] = mapped_column(String(1000), default="")
    technology: Mapped[str] = mapped_column(String(120), default="")
    risk_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    confidence: Mapped[str] = mapped_column(
        String(20), default=Confidence.MEDIUM.value, nullable=False
    )
    source_kind: Mapped[str] = mapped_column(
        String(20), default=SourceKind.DISCOVERED.value, nullable=False
    )
    #: Referenced somewhere but the artefact itself was never found.
    is_missing: Mapped[bool] = mapped_column(Boolean, default=False)
    #: False once a rescan confirms the discovery no longer exists (the file
    #: was deleted, or an edited file stopped producing it). Retired rows are
    #: kept for history but excluded from the graph. See ADR-005.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    #: Entity fields a human edited (via the API). Discovery must not clobber
    #: these on a later rescan. Empty means "no manual overrides".
    manual_fields_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    #: Stable natural key used to reconcile entities across rescans.
    fingerprint: Mapped[str] = mapped_column(String(600), nullable=False)
    meta_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    workspace: Mapped[Workspace] = relationship(back_populates="entities")

    @property
    def type(self) -> EntityType:
        return EntityType(self.entity_type)

    @property
    def display_name(self) -> str:
        return self.qualified_name or self.name


class Relationship(Base):
    """A directed, typed edge between two entities.

    Stored in English statement order: ``source --type--> target`` reads
    "source <verb> target". Influence direction is derived per type via
    :data:`atlas.domain.RELATIONSHIP_FLOW`.
    """

    __tablename__ = "relationships"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "source_id",
            "target_id",
            "relationship_type",
            "fingerprint",
            name="uq_relationship_fingerprint",
        ),
        Index("ix_rel_source", "workspace_id", "source_id"),
        Index("ix_rel_target", "workspace_id", "target_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    target_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    relationship_type: Mapped[str] = mapped_column(String(40), nullable=False)
    confidence: Mapped[str] = mapped_column(
        String(20), default=Confidence.MEDIUM.value, nullable=False
    )
    source_kind: Mapped[str] = mapped_column(
        String(20), default=SourceKind.DISCOVERED.value, nullable=False
    )
    review_status: Mapped[str] = mapped_column(
        String(20), default=ReviewStatus.PROPOSED.value, nullable=False
    )
    label: Mapped[str] = mapped_column(String(300), default="")
    fingerprint: Mapped[str] = mapped_column(String(600), default="")
    #: False once a rescan confirms the relationship no longer exists.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    meta_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    source: Mapped[Entity] = relationship(foreign_keys=[source_id])
    target: Mapped[Entity] = relationship(foreign_keys=[target_id])

    @property
    def type(self) -> RelationshipType:
        return RelationshipType(self.relationship_type)


class Evidence(Base):
    """Proof for a discovery.

    Exactly one of ``entity_id`` / ``relationship_id`` is set, enforced in the
    service layer (SQLite check constraints are not portable enough to rely on).
    """

    __tablename__ = "evidence"
    __table_args__ = (Index("ix_evidence_relationship", "relationship_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    entity_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("entities.id", ondelete="CASCADE"), nullable=True
    )
    relationship_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("relationships.id", ondelete="CASCADE"), nullable=True
    )
    subject_kind: Mapped[str] = mapped_column(
        String(20), default=SubjectKind.RELATIONSHIP.value, nullable=False
    )
    evidence_kind: Mapped[str] = mapped_column(
        String(40), default=EvidenceKind.SOURCE_LINE.value, nullable=False
    )
    source_path: Mapped[str] = mapped_column(String(1000), default="")
    line_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    line_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Always secret-redacted before it reaches persistence.
    snippet: Mapped[str] = mapped_column(Text, default="")
    parser: Mapped[str] = mapped_column(String(120), default="")
    confidence: Mapped[str] = mapped_column(
        String(20), default=Confidence.MEDIUM.value, nullable=False
    )
    meta_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    @property
    def kind(self) -> EvidenceKind:
        return EvidenceKind(self.evidence_kind)


class Scan(Base):
    """One discovery run over a filesystem root (or a demo seed)."""

    __tablename__ = "scans"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    root_path: Mapped[str] = mapped_column(String(1000), default="")
    status: Mapped[str] = mapped_column(
        String(20), default=ScanStatus.PENDING.value, nullable=False
    )
    scanner_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    diff_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    events: Mapped[list[ScanEvent]] = relationship(
        back_populates="scan", cascade="all, delete-orphan"
    )


class ScanEvent(Base):
    """Incremental progress/diff record for a scan."""

    __tablename__ = "scan_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    scan_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    subject_kind: Mapped[str] = mapped_column(String(20), default="")
    subject_ref: Mapped[str] = mapped_column(String(600), default="")
    message: Mapped[str] = mapped_column(Text, default="")
    details_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    scan: Mapped[Scan] = relationship(back_populates="events")


class RiskFinding(Base):
    """An explainable heuristic finding."""

    __tablename__ = "risk_findings"
    __table_args__ = (Index("ix_risk_workspace_severity", "workspace_id", "severity"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    rule_id: Mapped[str] = mapped_column(String(80), nullable=False)
    rule_name: Mapped[str] = mapped_column(String(200), nullable=False)
    severity: Mapped[str] = mapped_column(
        String(20), default=Severity.MEDIUM.value, nullable=False
    )
    title: Mapped[str] = mapped_column(String(400), nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="")
    entity_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("entities.id", ondelete="CASCADE"), nullable=True
    )
    relationship_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("relationships.id", ondelete="CASCADE"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default=RiskStatus.OPEN.value, nullable=False
    )
    details_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    @property
    def severity_level(self) -> Severity:
        return Severity(self.severity)


class SecretEvent(Base):
    """Record of a redacted secret. Stores only the shape, never the value."""

    __tablename__ = "secret_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    workspace_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True
    )
    source_path: Mapped[str] = mapped_column(String(1000), default="")
    line_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: e.g. ``password``, ``api_key``, ``jwt``, ``connection_string_password``
    secret_kind: Mapped[str] = mapped_column(String(80), default="")
    #: Redacted preview: ``Password=<redacted>``
    preview: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
