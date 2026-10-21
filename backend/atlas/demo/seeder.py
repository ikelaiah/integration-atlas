"""Persist demo and scan results into a workspace.

Both the demo seed and a real filesystem scan funnel through the same
:func:`apply_bundle` path so that persistence, fingerprinting and secret
redaction behave identically.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from atlas.demo.northstar import EntitySpec, RelSpec, build_demo, redacted_snippet
from atlas.domain import Confidence, ReviewStatus, SourceKind, SubjectKind
from atlas.models import (
    Entity,
    Evidence,
    Relationship,
    RiskFinding,
    Scan,
    SecretEvent,
    Workspace,
)
from atlas.services.graph import GraphIndex
from atlas.services.redaction import redact_value
from atlas.services.risk import RiskContext, drafts_to_rows, run_rules

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_UNC_RE = re.compile(r"^//[^/]+")


def slugify(value: str) -> str:
    normalised = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return _SLUG_RE.sub("-", normalised.lower()).strip("-") or "workspace"


def path_tail(location: str, segments: int = 3) -> str:
    """Normalise a filesystem reference down to its last few segments.

    The same artefact is written differently depending on who discovered it:
    a directory walk yields an absolute path, a Task Scheduler export yields
    ``C:\\integrations\\student\\export_students.ps1``, and a config file may
    yield a POSIX-style path. Comparing only the tail keeps those views
    together while still distinguishing same-named files in different folders.

    This is used for *unscoped* references only. A machine-local artefact has a
    server scope and is compared by its full canonical path instead: two
    unrelated folders can easily share the same three trailing segments.
    """
    cleaned = (location or "").replace("\\", "/").strip()
    cleaned = _UNC_RE.sub("", cleaned)
    cleaned = _DRIVE_RE.sub("", cleaned)
    parts = [p for p in cleaned.split("/") if p and p != "."]
    return "/".join(parts[-segments:]).lower()


def canonical_path(location: str, *, windows: bool | None = None) -> str:
    """Return the full canonical form of a path used for server-scoped identity.

    Unlike :func:`path_tail` this keeps *every* segment, preserves a Windows
    drive letter, folds path separators and collapses repeated separators. When
    ``windows`` is true the path is case-folded (Windows filesystems are
    case-insensitive); when it is false the case is preserved (Linux is
    case-sensitive). ``windows=None`` infers the style from a drive letter.
    """
    value = (location or "").strip().strip("\"'")
    value = value.replace("\\", "/")
    if value.startswith("//"):
        # Preserve the UNC introducer while collapsing the rest.
        value = "//" + re.sub(r"/{2,}", "/", value[2:])
    else:
        value = re.sub(r"/{2,}", "/", value)
    if windows is None:
        windows = bool(_DRIVE_RE.match(value))
    if windows:
        value = value.lower()
    if len(value) > 1:
        value = value.rstrip("/")
    return value


def fingerprint_entity(
    entity_type: str,
    qualified_name: str,
    name: str,
    location: str,
    *,
    scope: str | None = None,
    windows: bool | None = None,
) -> str:
    """Stable natural key so entities survive rescans and reseeds.

    Unscoped artefacts are compared by path suffix so the same reference
    written through different notations unifies into one entity. A
    server-scoped artefact is machine-local: its identity is the execution
    server plus the *full canonical original path*, so two different folders on
    one host never merge and the same path on two hosts never merges.

    ``windows`` selects case folding for the scoped path; ``None`` infers it
    from a drive letter.
    """
    if scope:
        identity = canonical_path(qualified_name or name, windows=windows)
        if not identity:
            identity = (qualified_name or name).strip().lower()
        prefix = f"{scope.strip().lower()}|"
        return f"{prefix}{entity_type}|{identity}"[:600]

    # UNC paths name a resource on a remote host. Keep the host and every path
    # segment so different shares never collapse to the same suffix. UNC names
    # are case-insensitive, regardless of the execution host's operating system.
    remote_path = qualified_name or location or name
    if remote_path.replace("\\", "/").startswith("//"):
        identity = canonical_path(remote_path, windows=True)
        return f"{entity_type}|remote:{identity}"[:600]

    identity = (qualified_name or name).strip().lower()
    if "/" in identity or "\\" in identity:
        identity = path_tail(identity) or identity
    tail = path_tail(location)
    core = f"{entity_type}|{identity}|{tail}"
    return core[:600]


def recompute_entity_fingerprint(entity: Entity) -> str:
    """Recompute the fingerprint an entity would get under the current rules.

    Server-scoped rows store their scope as a ``<server>::`` prefix on
    ``qualified_name`` plus ``server``/``server_os`` metadata, so a migration
    can derive the canonical server-scoped fingerprint from persisted fields
    without asking a scanner to run again.
    """
    meta = entity.meta_json or {}
    server = str(meta.get("server") or "").strip()
    qualified = entity.qualified_name or ""
    scope: str | None = None
    prefix, separator, remainder = qualified.partition("::")
    if separator and server and prefix.strip().lower() == server.lower():
        scope = server.lower()
        qualified = remainder

    windows: bool | None = None
    os_name = str(meta.get("server_os") or "").strip()
    if os_name:
        windows = os_name.lower().startswith("win")

    return fingerprint_entity(
        entity.entity_type,
        qualified,
        entity.name,
        entity.location or "",
        scope=scope,
        windows=windows,
    )


def upgrade_legacy_fingerprints(session: Session, *, workspace_id: str | None = None) -> int:
    """Re-key rows written before server-scoped identities used full paths.

    Every entity's fingerprint is recomputed from its persisted fields and
    rewritten in place when it changed; discovered relationships are re-keyed
    to match. Manual rows and evidence are never deleted, and the operation is
    idempotent. A row whose new identity is already owned by another entity is
    left untouched rather than clobbering the owner — the normaliser also
    considers the recomputed key when loading, so it still reconciles.
    """
    entity_stmt = select(Entity).order_by(Entity.id)
    if workspace_id:
        entity_stmt = entity_stmt.where(Entity.workspace_id == workspace_id)
    entities = list(session.scalars(entity_stmt))
    # Fingerprints are unique per workspace, not globally; track occupancy per
    # workspace so a collision in one workspace never blocks another.
    occupied: dict[str, set[str]] = {}
    for entity in entities:
        occupied.setdefault(entity.workspace_id, set()).add(entity.fingerprint)

    changed = 0
    for entity in entities:
        new_fingerprint = recompute_entity_fingerprint(entity)
        if new_fingerprint == entity.fingerprint:
            continue
        bucket = occupied.setdefault(entity.workspace_id, set())
        if new_fingerprint in bucket:
            continue
        bucket.discard(entity.fingerprint)
        entity.fingerprint = new_fingerprint
        bucket.add(new_fingerprint)
        changed += 1
        session.flush()

    relationship_stmt = select(Relationship).order_by(Relationship.id)
    if workspace_id:
        relationship_stmt = relationship_stmt.where(
            Relationship.workspace_id == workspace_id
        )
    for relationship in session.scalars(relationship_stmt):
        if relationship.source_kind == SourceKind.MANUAL.value:
            continue
        source = session.get(Entity, relationship.source_id)
        target = session.get(Entity, relationship.target_id)
        if source is None or target is None:
            continue
        new_fingerprint = fingerprint_relationship(
            source.fingerprint,
            target.fingerprint,
            relationship.relationship_type,
            relationship.label or "",
        )
        if new_fingerprint != relationship.fingerprint:
            relationship.fingerprint = new_fingerprint
            changed += 1

    session.flush()
    return changed


def fingerprint_relationship(
    source_fp: str, target_fp: str, relationship_type: str, label: str
) -> str:
    return f"{source_fp}->{relationship_type}->{target_fp}|{label}"[:600]


@dataclass
class ApplyResult:
    workspace_id: str
    entities_added: int = 0
    entities_updated: int = 0
    entities_removed: int = 0
    relationships_added: int = 0
    relationships_updated: int = 0
    relationships_removed: int = 0
    evidence_added: int = 0
    secrets_redacted: int = 0
    risks_found: int = 0
    unchanged: int = 0
    entity_ids: dict[str, str] = field(default_factory=dict)
    kept_workspace_id: str | None = None
    kept_workspace_name: str | None = None

    def as_dict(self) -> dict:
        return {
            "workspace_id": self.workspace_id,
            "kept_workspace_id": self.kept_workspace_id,
            "kept_workspace_name": self.kept_workspace_name,
            "entities_added": self.entities_added,
            "entities_updated": self.entities_updated,
            "entities_removed": self.entities_removed,
            "relationships_added": self.relationships_added,
            "relationships_updated": self.relationships_updated,
            "relationships_removed": self.relationships_removed,
            "evidence_added": self.evidence_added,
            "secrets_redacted": self.secrets_redacted,
            "risks_found": self.risks_found,
            "unchanged": self.unchanged,
        }


def get_or_create_workspace(
    session: Session,
    name: str,
    *,
    description: str = "",
    is_demo: bool = False,
    slug: str | None = None,
) -> Workspace:
    resolved_slug = slug or slugify(name)
    existing = session.scalar(select(Workspace).where(Workspace.slug == resolved_slug))
    if existing is not None:
        return existing
    workspace = Workspace(name=name, slug=resolved_slug, description=description, is_demo=is_demo)
    session.add(workspace)
    session.flush()
    return workspace


def apply_bundle(
    session: Session,
    workspace: Workspace,
    entities: list[EntitySpec],
    relationships: list[RelSpec],
    *,
    source_kind: SourceKind = SourceKind.DEMO,
    replace: bool = False,
) -> ApplyResult:
    """Write an entity/relationship bundle into ``workspace``.

    ``replace=True`` wipes existing discoveries first (used when reseeding the
    demo). Otherwise existing rows are matched by fingerprint and updated in
    place so manual knowledge and prior scans are not lost.
    """
    result = ApplyResult(workspace_id=workspace.id)

    if replace:
        for rel in session.scalars(
            select(Relationship).where(Relationship.workspace_id == workspace.id)
        ):
            session.delete(rel)
        for entity in session.scalars(
            select(Entity).where(Entity.workspace_id == workspace.id)
        ):
            session.delete(entity)
        session.flush()

    existing_entities = {
        e.fingerprint: e
        for e in session.scalars(select(Entity).where(Entity.workspace_id == workspace.id))
    }
    existing_relationships = {
        r.fingerprint: r
        for r in session.scalars(select(Relationship).where(Relationship.workspace_id == workspace.id))
    }

    by_key: dict[str, Entity] = {}
    fingerprints: dict[str, str] = {}

    for spec in entities:
        fp = fingerprint_entity(
            spec.entity_type.value, spec.qualified_name, spec.name, spec.location
        )
        fingerprints[spec.key] = fp
        payload = {
            "entity_type": spec.entity_type.value,
            "name": redacted_snippet(spec.name),
            "qualified_name": redacted_snippet(spec.qualified_name or spec.name),
            "description": redacted_snippet(spec.description),
            "owner": redacted_snippet(spec.owner),
            "environment": spec.environment.value,
            "location": redacted_snippet(spec.location),
            "technology": redacted_snippet(spec.technology),
            "confidence": spec.confidence.value,
            "is_missing": spec.is_missing,
            "is_active": True,
            "meta_json": redact_value(spec.meta or {}, "meta"),
            "source_kind": source_kind.value,
            "fingerprint": fp,
        }
        row = existing_entities.get(fp)
        if row is None:
            row = Entity(workspace_id=workspace.id, **payload)
            session.add(row)
            result.entities_added += 1
        else:
            protected: set[str] = set()
            if row.source_kind == SourceKind.MANUAL.value:
                protected = set(row.manual_fields_json or []) or {"description", "owner"}
            changed = False
            for field_name, value in payload.items():
                if field_name == "source_kind" and row.source_kind == SourceKind.MANUAL.value:
                    continue
                if field_name in protected:
                    continue
                if getattr(row, field_name) != value:
                    setattr(row, field_name, value)
                    changed = True
            if changed:
                result.entities_updated += 1
            else:
                result.unchanged += 1
        session.flush()
        by_key[spec.key] = row
        result.entity_ids[spec.key] = row.id

    for spec in relationships:
        source = by_key.get(spec.source)
        target = by_key.get(spec.target)
        if source is None or target is None:
            continue
        fp = fingerprint_relationship(
            fingerprints[spec.source], fingerprints[spec.target], spec.rel_type.value, spec.label
        )
        payload = {
            "relationship_type": spec.rel_type.value,
            "confidence": spec.confidence.value,
            "label": redacted_snippet(spec.label),
            "source_kind": source_kind.value,
            "review_status": ReviewStatus.PROPOSED.value
            if spec.confidence is not Confidence.CONFIRMED
            else ReviewStatus.CONFIRMED.value,
            "fingerprint": fp,
        }
        rel_row = existing_relationships.get(fp)
        if rel_row is None:
            rel_row = Relationship(
                workspace_id=workspace.id,
                source_id=source.id,
                target_id=target.id,
                **payload,
            )
            session.add(rel_row)
            session.flush()
            result.relationships_added += 1
        else:
            changed = False
            for field_name, value in payload.items():
                if getattr(rel_row, field_name) != value:
                    setattr(rel_row, field_name, value)
                    changed = True
            if changed:
                result.relationships_updated += 1

        for ev_spec in spec.evidence:
            snippet = redacted_snippet(ev_spec.snippet)
            redactions = len(redacted_snippet(ev_spec.snippet)) != len(ev_spec.snippet)
            session.add(
                Evidence(
                    workspace_id=workspace.id,
                    relationship_id=rel_row.id,
                    subject_kind=SubjectKind.RELATIONSHIP.value,
                    evidence_kind=ev_spec.kind.value,
                    source_path=ev_spec.path,
                    line_start=ev_spec.line,
                    snippet=snippet,
                    parser=ev_spec.parser,
                    confidence=ev_spec.confidence.value,
                )
            )
            result.evidence_added += 1
            if redactions:
                result.secrets_redacted += 1
                session.add(
                    SecretEvent(
                        workspace_id=workspace.id,
                        source_path=ev_spec.path,
                        line_start=ev_spec.line,
                        secret_kind="credential",
                        preview=snippet[:120],
                    )
                )
    session.flush()
    return result


def run_risk_analysis(session: Session, workspace: Workspace) -> int:
    """(Re)generate explainable risk findings for a workspace."""
    entities = list(
        session.scalars(
            select(Entity).where(
                Entity.workspace_id == workspace.id, Entity.is_active.is_(True)
            )
        )
    )
    relationships = list(
        session.scalars(
            select(Relationship).where(
                Relationship.workspace_id == workspace.id,
                Relationship.is_active.is_(True),
            )
        )
    )
    index = GraphIndex(entities, relationships)
    drafts = run_rules(RiskContext(index=index, entities=entities))

    for existing in session.scalars(
        select(RiskFinding).where(RiskFinding.workspace_id == workspace.id)
    ):
        session.delete(existing)
    session.flush()

    rows = drafts_to_rows(drafts, workspace.id)
    for row in rows:
        session.add(row)
    session.flush()
    return len(rows)


DEMO_NAME = "Northstar Education Group"
DEMO_SLUG = "northstar-education-group"
DEMO_DESCRIPTION = (
    "Fictional demo estate: legacy SIS, enrolment portal, finance ERP and SaaS integrations."
)


class DemoWorkspaceError(ValueError):
    """Raised when an operation would put non-demo data into the demo workspace."""


def find_demo_workspace(session: Session) -> Workspace | None:
    return session.scalar(
        select(Workspace).where(Workspace.is_demo.is_(True)).order_by(Workspace.created_at)
    )


def _unique_slug(session: Session, base: str) -> str:
    slug, suffix = base, 2
    while session.scalar(select(Workspace.id).where(Workspace.slug == slug)) is not None:
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


@dataclass
class DemoStatus:
    """What a demo reset would restore, and what it would keep aside."""

    workspace: Workspace | None
    demo_entities: int
    demo_relationships: int
    edited_entities: int = 0
    reviewed_relationships: int = 0
    scans: int = 0
    other_entities: int = 0
    other_relationships: int = 0

    @property
    def has_other_data(self) -> bool:
        return bool(self.scans or self.other_entities or self.other_relationships)


def _demo_fingerprints() -> tuple[set[str], dict[str, str]]:
    """Entity fingerprints and each relationship's seeded review status."""
    bundle = build_demo()
    entity_fps: dict[str, str] = {}
    for spec in bundle.entities:
        entity_fps[spec.key] = fingerprint_entity(
            spec.entity_type.value, spec.qualified_name, spec.name, spec.location
        )
    relationships: dict[str, str] = {}
    for spec in bundle.relationships:
        if spec.source not in entity_fps or spec.target not in entity_fps:
            continue
        fp = fingerprint_relationship(
            entity_fps[spec.source], entity_fps[spec.target], spec.rel_type.value, spec.label
        )
        relationships[fp] = (
            ReviewStatus.CONFIRMED.value
            if spec.confidence is Confidence.CONFIRMED
            else ReviewStatus.PROPOSED.value
        )
    return set(entity_fps.values()), relationships


def demo_status(session: Session) -> DemoStatus:
    entity_fps, relationship_status = _demo_fingerprints()
    status = DemoStatus(
        workspace=find_demo_workspace(session),
        demo_entities=len(entity_fps),
        demo_relationships=len(relationship_status),
    )
    workspace = status.workspace
    if workspace is None:
        return status
    for entity in session.scalars(select(Entity).where(Entity.workspace_id == workspace.id)):
        if entity.fingerprint not in entity_fps:
            status.other_entities += 1
        elif entity.manual_fields_json:
            status.edited_entities += 1
    for rel in session.scalars(
        select(Relationship).where(Relationship.workspace_id == workspace.id)
    ):
        seeded = relationship_status.get(rel.fingerprint)
        if seeded is None:
            status.other_relationships += 1
        elif rel.review_status != seeded:
            status.reviewed_relationships += 1
    status.scans = len(
        list(session.scalars(select(Scan.id).where(Scan.workspace_id == workspace.id)))
    )
    return status


def kept_workspace_name(session: Session) -> tuple[str, str]:
    """A unique name and slug for a demo workspace kept aside by a reset."""
    base = f"{DEMO_NAME} (kept {date.today().isoformat()})"
    name, suffix = base, 2
    while session.scalar(select(Workspace.id).where(Workspace.slug == slugify(name))) is not None:
        name = f"{base} {suffix}"
        suffix += 1
    return name, slugify(name)


def seed_northstar_demo(session: Session, *, replace: bool = True) -> ApplyResult:
    """Load the Northstar demo into the demo workspace.

    ``replace=True`` restores the original demo data. Data that did not come
    from the demo is never deleted: if the demo workspace holds scan history or
    rows outside the Northstar bundle, that workspace is kept as a regular
    workspace and a fresh demo workspace is created beside it.
    """
    bundle = build_demo()
    kept: Workspace | None = None
    workspace = find_demo_workspace(session)
    if replace and workspace is not None and demo_status(session).has_other_data:
        kept = workspace
        kept.is_demo = False
        kept.name, kept.slug = kept_workspace_name(session)
        kept.description = (
            "Kept when the demo was reset because this workspace held scan results "
            "or data added outside the demo."
        )
        session.flush()
        workspace = None
    if workspace is None:
        workspace = Workspace(
            name=DEMO_NAME,
            slug=_unique_slug(session, DEMO_SLUG),
            description=DEMO_DESCRIPTION,
            is_demo=True,
        )
        session.add(workspace)
        session.flush()
    result = apply_bundle(
        session,
        workspace,
        bundle.entities,
        bundle.relationships,
        source_kind=SourceKind.DEMO,
        replace=replace,
    )
    result.risks_found = run_risk_analysis(session, workspace)
    if kept is not None:
        result.kept_workspace_id = kept.id
        result.kept_workspace_name = kept.name
    return result


def resolve_scan_workspace(
    session: Session,
    *,
    workspace_id: str | None,
    workspace_name: str | None,
    default_name: str,
    description: str = "",
) -> Workspace:
    """Find or create the workspace a scan writes to; never the demo.

    ``workspace_id`` may be an id or a slug. Raises ``LookupError`` for an
    unknown id and :class:`DemoWorkspaceError` for the demo workspace.
    """
    if workspace_id:
        workspace = session.scalar(
            select(Workspace).where(
                (Workspace.id == workspace_id) | (Workspace.slug == workspace_id)
            )
        )
        if workspace is None:
            raise LookupError("Workspace not found")
    else:
        name = (workspace_name or "").strip() or default_name
        workspace = session.scalar(select(Workspace).where(Workspace.slug == slugify(name)))
        if workspace is None:
            workspace = get_or_create_workspace(session, name, description=description)
    if workspace.is_demo:
        raise DemoWorkspaceError(
            f"{workspace.name} is the demo workspace and only holds Northstar demo data. "
            "Scan into a workspace of your own instead."
        )
    return workspace


def demo_entity_count() -> tuple[int, int]:
    bundle = build_demo()
    return len(bundle.entities), len(bundle.relationships)
