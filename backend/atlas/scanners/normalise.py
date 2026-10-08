"""Normalise scanner findings into persisted entities, relationships and evidence.

This is where the important guarantees live:

* **Identity.** Every entity gets a stable fingerprint so a rescan reconciles
  rather than duplicates. Server-scoped identities (see :mod:`atlas.scanners.
  server_bundle`) fold the execution host into the fingerprint so identical
  artefacts on different machines never merge.
* **Redaction.** Every field that can carry an operator's secret — snippet,
  description, location, qualified name and nested metadata — passes through
  :mod:`atlas.services.redaction` before it can reach a row or an export.
* **Evidence.** Every relationship carries at least one evidence row naming
  the file and line that produced it.
* **Reconciliation.** A rescan upserts by fingerprint, preserves manual edits
  and provenance, and retires discoveries that the scan has confirmed are
  gone without touching manual knowledge or artefacts supported elsewhere.

Scanners emit *candidates*; the normaliser decides what those candidates
become. Keeping that boundary sharp is what makes new language support cheap.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from atlas.demo.seeder import (
    fingerprint_entity,
    fingerprint_relationship,
    recompute_entity_fingerprint,
    upgrade_legacy_fingerprints,
)
from atlas.domain import (
    Confidence,
    EntityType,
    Environment,
    RelationshipType,
    ReviewStatus,
    SourceKind,
    SubjectKind,
)
from atlas.models import Entity, Evidence, Relationship, SecretEvent, Workspace
from atlas.scanners.base import (
    EntityCandidate,
    RelationshipCandidate,
    ScanResult,
)
from atlas.services.redaction import redact, redact_value

if TYPE_CHECKING:  # pragma: no cover - import cycle guarded for type checkers
    from atlas.scanners.server_bundle import ServerInfo

_SLUG = re.compile(r"[^0-9a-zA-Z]+")

#: Entity types whose identity is local to a machine and therefore scoped by
#: the execution server when a server bundle declares one.
_SERVER_SCOPED_TYPES: frozenset[EntityType] = frozenset(
    {
        EntityType.SCRIPT,
        EntityType.SCHEDULED_JOB,
        EntityType.FILE,
        EntityType.DIRECTORY,
    }
)


# --------------------------------------------------------------------------- #
# Reference helpers used by the scanners
# --------------------------------------------------------------------------- #
def host_of(url: str) -> str:
    try:
        parsed = urlparse(url if "://" in url else f"//{url}", scheme="")
        return (parsed.hostname or parsed.netloc or "").lower()
    except Exception:  # noqa: BLE001
        return ""


def path_of(url: str) -> str:
    try:
        return urlparse(url).path or ""
    except Exception:  # noqa: BLE001
        return ""


def normalise_path_ref(raw: str) -> str:
    """Turn an arbitrary path literal into a stable reference."""
    value = raw.strip().strip("\"'").replace("\\", "/")
    if value.startswith("//"):
        value = "//" + re.sub(r"/{2,}", "/", value[2:])
    else:
        value = re.sub(r"/+", "/", value)
    return value


def _environment_value(raw: str) -> str:
    if not raw:
        return Environment.UNKNOWN.value
    try:
        return Environment(str(raw).strip().lower()).value
    except ValueError:
        return Environment.UNKNOWN.value


def _normalise_ref(value: str, *, case_sensitive: bool = False) -> str:
    """Fold path separators and optionally preserve filesystem case."""
    normalised = value.replace("\\", "/")
    return normalised if case_sensitive else normalised.lower()


_URL_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]+://")


def is_local_path(location: str) -> bool:
    """True for a path that names a resource on the local machine.

    UNC shares (``//host/share``) and URLs point at *other* machines, so they
    are never scoped to the execution server — they are dependencies.
    """
    loc = (location or "").strip().replace("\\", "/")
    if not loc:
        return False
    if loc.startswith("//"):
        return False
    loc = re.sub(r"/+", "/", loc)
    # A single-letter "scheme" is a Windows drive (C:/...), not a URL.
    return not _URL_SCHEME.match(loc)


# --------------------------------------------------------------------------- #
# Normalisation
# --------------------------------------------------------------------------- #
@dataclass
class NormaliseStats:
    entities_added: int = 0
    entities_updated: int = 0
    entities_removed: int = 0
    relationships_added: int = 0
    relationships_updated: int = 0
    relationships_removed: int = 0
    evidence_added: int = 0
    secrets_redacted: int = 0
    warnings: int = 0
    unmatched_refs: int = 0

    def as_dict(self) -> dict:
        return {
            "entities_added": self.entities_added,
            "entities_updated": self.entities_updated,
            "entities_removed": self.entities_removed,
            "relationships_added": self.relationships_added,
            "relationships_updated": self.relationships_updated,
            "relationships_removed": self.relationships_removed,
            "evidence_added": self.evidence_added,
            "secrets_redacted": self.secrets_redacted,
            "warnings": self.warnings,
            "unmatched_refs": self.unmatched_refs,
        }


@dataclass
class _EntityKey:
    entity_type: str
    qualified_name: str


class Normaliser:
    def __init__(self, session, workspace: Workspace, *, source_kind: SourceKind = SourceKind.DISCOVERED):
        self.session = session
        self.workspace = workspace
        self.source_kind = source_kind
        self.stats = NormaliseStats()
        self._by_fingerprint: dict[str, Entity] = {}
        self._by_ref: dict[str, list[Entity]] = {}
        self._rel_fingerprints: set[str] = set()
        self._relationships: dict[str, Relationship] = {}
        self._server_entities: dict[str, Entity] = {}
        self.observed_entity_ids: set[str] = set()
        self.observed_relationship_ids: set[str] = set()
        # Bring fingerprints written before server-scoped identities used full
        # canonical paths up to date before reconciling against them.
        upgrade_legacy_fingerprints(self.session, workspace_id=self.workspace.id)
        self._load_existing()

    def _load_existing(self) -> None:
        from sqlalchemy import select

        for entity in self.session.scalars(
            select(Entity).where(Entity.workspace_id == self.workspace.id)
        ):
            self._by_fingerprint[entity.fingerprint] = entity
            # A row whose persisted key predates the current rules still
            # answers to the key it would get today, so a rescan reconciles
            # with it in place instead of duplicating it.
            recomputed = recompute_entity_fingerprint(entity)
            if recomputed != entity.fingerprint:
                self._by_fingerprint.setdefault(recomputed, entity)
            self._index_ref(entity)

        for rel in self.session.scalars(
            select(Relationship).where(Relationship.workspace_id == self.workspace.id)
        ):
            self._rel_fingerprints.add(rel.fingerprint)
            self._relationships[rel.id] = rel

    def _index_ref(self, entity: Entity) -> None:
        raw_keys = [entity.name, entity.qualified_name]
        # A server-scoped identity also answers to its un-scoped form, so a
        # reference written as ``/opt/sync.py`` matches the entity stored as
        # ``APP01::/opt/sync.py``. Cross-server collisions are resolved by the
        # server filter, never by the index.
        if self._server_of(entity) and "::" in (entity.qualified_name or ""):
            raw_keys.append(entity.qualified_name.split("::", 1)[1])
        raw_keys.append(entity.fingerprint)

        meta = entity.meta_json or {}
        server_os = str(meta.get("server_os") or "").lower()
        case_sensitive = (
            entity.entity_type in {kind.value for kind in _SERVER_SCOPED_TYPES}
            and server_os.startswith("linux")
        )
        keys: set[str] = set()
        for key in raw_keys:
            if not key:
                continue
            keys.add(_normalise_ref(key, case_sensitive=case_sensitive))
        for key in keys:
            bucket = self._by_ref.setdefault(key, [])
            if entity not in bucket:
                bucket.append(entity)

    def _lookup(
        self,
        ref: str,
        hint: EntityType | None,
        server: ServerInfo | None,
    ) -> list[Entity]:
        """Return every candidate a single reference spelling could mean."""
        case_sensitive = bool(
            server
            and server.os.strip().lower().startswith("linux")
            and hint in _SERVER_SCOPED_TYPES
            and is_local_path(ref)
        )
        seen: dict[str, Entity] = {}
        for variant in (
            _normalise_ref(ref.strip(), case_sensitive=case_sensitive),
        ):
            for candidate in self._by_ref.get(variant, []):
                seen.setdefault(candidate.id, candidate)
        candidates = list(seen.values())
        if not candidates:
            return []

        if hint is not None:
            # A typed reference may only resolve to that type. Falling back to
            # other types is what let a cron job resolve to itself.
            candidates = [c for c in candidates if c.entity_type == hint.value]
            if not candidates:
                return []

        if server is not None:
            server_key = server.hostname.lower()
            same_server = [c for c in candidates if self._server_of(c) == server_key]
            unscoped = [c for c in candidates if not self._server_of(c)]
            if hint in _SERVER_SCOPED_TYPES:
                # Local resources are isolated: server B never borrows server
                # A's script, and a miss becomes a B-scoped placeholder. A
                # remote UNC share or URL is a shared dependency, so it
                # resolves against unscoped identities regardless of which job
                # found the reference.
                candidates = same_server if is_local_path(ref) else unscoped
            else:
                candidates = same_server or unscoped
            if not candidates:
                return []

        return candidates

    def _pick(
        self,
        candidates: list[Entity],
        hint: EntityType | None,
        server: ServerInfo | None,
    ) -> Entity | None:
        if not candidates:
            return None
        discovered = [c for c in candidates if not c.is_missing]
        pool = discovered or candidates
        # For a server-scoped local resource, ambiguity is preserved rather
        # than resolved to an unrelated same-named script.
        if server is not None and hint in _SERVER_SCOPED_TYPES and len({c.id for c in pool}) > 1:
            return None
        pool = sorted(pool, key=lambda c: (c.entity_type, c.qualified_name, c.id))
        return pool[0]

    # -- server scope ----------------------------------------------------- #
    @staticmethod
    def _server_of(entity: Entity) -> str:
        meta = entity.meta_json or {}
        return str(meta.get("server", "")).lower()

    def _scope_name(self, candidate: EntityCandidate, server: ServerInfo | None) -> str | None:
        """Return the execution-server scope for a candidate, or ``None``."""
        if server is None:
            return None
        if candidate.entity_type is EntityType.SCHEDULED_JOB:
            return server.hostname.lower()
        if candidate.entity_type in _SERVER_SCOPED_TYPES:
            location = candidate.location or candidate.qualified_name or candidate.name
            if is_local_path(location):
                return server.hostname.lower()
        return None

    # -- entities --------------------------------------------------------- #
    def upsert_entity(
        self, candidate: EntityCandidate, server: ServerInfo | None = None
    ) -> Entity:
        snippet = redact(candidate.snippet or "").text
        description = redact(candidate.description or "").text
        location = redact(candidate.location or "").text

        qualified = redact(candidate.qualified_name or candidate.name).text
        name = redact(candidate.name).text

        meta = redact_value(candidate.meta or {}, "meta")
        if not isinstance(meta, dict):
            meta = {}

        base_qualified = qualified
        scope = self._scope_name(candidate, server)
        windows: bool | None = None
        if scope:
            qualified = f"{scope}::{qualified}"
            meta["server"] = server.hostname  # type: ignore[union-attr]
            if getattr(server, "fqdn", ""):
                meta["server_fqdn"] = server.fqdn  # type: ignore[union-attr]
            if getattr(server, "os", ""):
                meta["server_os"] = server.os  # type: ignore[union-attr]
                windows = server.os.strip().lower().startswith("win")  # type: ignore[union-attr]
            meta["execution_server_known"] = True

        fp = fingerprint_entity(
            candidate.entity_type.value,
            base_qualified,
            name,
            location,
            scope=scope,
            windows=windows,
        )

        payload = {
            "entity_type": candidate.entity_type.value,
            "name": name,
            "qualified_name": qualified,
            "description": description,
            "owner": redact(candidate.owner or "").text,
            "location": location,
            "technology": redact(candidate.technology or "").text,
            "confidence": candidate.confidence.value,
            "is_missing": candidate.is_missing,
            "is_active": True,
            "meta_json": meta,
            "source_kind": self.source_kind.value,
            "fingerprint": fp,
        }

        existing = self._by_fingerprint.get(fp)
        if existing is None:
            entity = Entity(workspace_id=self.workspace.id, **payload)
            self.session.add(entity)
            self.session.flush()
            self._by_fingerprint[fp] = entity
            self.stats.entities_added += 1
        elif candidate.is_missing and not existing.is_missing:
            # A missing placeholder is the weakest possible statement about an
            # artefact. It must never downgrade a discovered entity's
            # is_missing state, confidence, metadata or provenance.
            entity = existing
        else:
            entity = existing
            if self._apply_payload(entity, payload):
                self.stats.entities_updated += 1

        self.observed_entity_ids.add(entity.id)
        self._by_fingerprint.setdefault(fp, entity)
        self._index_ref(entity)

        if candidate.snippet or candidate.source_path:
            self.session.add(
                Evidence(
                    workspace_id=self.workspace.id,
                    entity_id=entity.id,
                    subject_kind=SubjectKind.ENTITY.value,
                    evidence_kind=candidate.evidence_kind.value,
                    source_path=candidate.source_path,
                    line_start=candidate.line,
                    snippet=snippet,
                    parser=candidate.parser or "scanner",
                    confidence=candidate.confidence.value,
                )
            )
            self.stats.evidence_added += 1

        return entity

    def _apply_payload(self, entity: Entity, payload: dict[str, Any]) -> bool:
        """Update ``entity`` from ``payload`` while preserving manual knowledge."""
        protected: set[str] = set()
        if entity.source_kind == SourceKind.MANUAL.value:
            protected = set(entity.manual_fields_json or []) or {"description", "owner"}

        changed = False
        for field_name, value in payload.items():
            if field_name == "source_kind" and entity.source_kind == SourceKind.MANUAL.value:
                continue
            if field_name in protected:
                continue
            if getattr(entity, field_name) != value:
                setattr(entity, field_name, value)
                changed = True
        return changed

    # -- relationships ---------------------------------------------------- #
    def upsert_relationship(
        self,
        candidate: RelationshipCandidate,
        source: Entity,
        target: Entity,
        server: ServerInfo | None = None,
    ) -> Relationship:
        snippet = redact(candidate.snippet or "").text
        fp = fingerprint_relationship(
            source.fingerprint, target.fingerprint, candidate.relationship_type.value, candidate.label
        )

        if fp in self._rel_fingerprints:
            from sqlalchemy import select

            row = self.session.scalar(
                select(Relationship).where(
                    Relationship.workspace_id == self.workspace.id,
                    Relationship.fingerprint == fp,
                )
            )
            if row is not None:
                if not row.is_active:
                    row.is_active = True
                self.observed_relationship_ids.add(row.id)
                self._add_evidence(row, candidate, snippet)
                return row

        relationship = Relationship(
            workspace_id=self.workspace.id,
            source_id=source.id,
            target_id=target.id,
            relationship_type=candidate.relationship_type.value,
            confidence=candidate.confidence.value,
            source_kind=self.source_kind.value,
            review_status=ReviewStatus.CONFIRMED.value
            if candidate.confidence is Confidence.CONFIRMED
            else ReviewStatus.PROPOSED.value,
            label=candidate.label,
            is_active=True,
            fingerprint=fp,
        )
        self.session.add(relationship)
        self.session.flush()
        self._rel_fingerprints.add(fp)
        self._relationships[relationship.id] = relationship
        self.stats.relationships_added += 1
        self._add_evidence(relationship, candidate, snippet)
        self.observed_relationship_ids.add(relationship.id)
        return relationship

    def _add_evidence(self, relationship: Relationship, candidate: RelationshipCandidate, snippet: str) -> None:
        if not (candidate.snippet or candidate.source_path):
            return
        self.session.add(
            Evidence(
                workspace_id=self.workspace.id,
                relationship_id=relationship.id,
                subject_kind=SubjectKind.RELATIONSHIP.value,
                evidence_kind=candidate.evidence_kind.value,
                source_path=candidate.source_path,
                line_start=candidate.line,
                snippet=snippet,
                parser=candidate.parser or "scanner",
                confidence=candidate.confidence.value,
            )
        )
        self.stats.evidence_added += 1

    # -- references ------------------------------------------------------- #
    def resolve(
        self,
        ref: str,
        hint: EntityType | None = None,
        server: ServerInfo | None = None,
    ) -> Entity | None:
        """Find the entity a scanner reference points at.

        Tries exact name, qualified name, then the tail of a dotted/path
        reference. Unresolved references become *missing* entities so the
        user can see that something depends on an artefact nobody found.
        """
        if not ref:
            return None
        cleaned = redact(ref).text
        case_sensitive = bool(
            server
            and server.os.strip().lower().startswith("linux")
            and hint in _SERVER_SCOPED_TYPES
            and is_local_path(cleaned)
        )
        key = _normalise_ref(cleaned.strip(), case_sensitive=case_sensitive)

        # 1. Canonical full reference (server identity + full original path).
        found = self._pick(self._lookup(key, hint, server), hint, server)
        if found is not None:
            return found

        # 2. Basename fallback, only for a *local* reference and only when it
        # is unambiguous. A remote path is an exact shared identity: falling
        # back to its basename would collapse distinct shares.
        tail = key.replace("\\", "/").rstrip("/").split("/")[-1]
        if tail and tail != key and is_local_path(key):
            found = self._pick(self._lookup(tail, hint, server), hint, server)
            if found is not None:
                return found

        # 3. Dotted qualified-name tail match: Student.Person -> Person
        if "." in key and "/" not in key:
            dotted = key.split(".")[-1]
            if dotted and dotted not in {key, tail}:
                found = self._pick(self._lookup(dotted, hint, server), hint, server)
                if found is not None:
                    return found

        return None

    def ensure_missing(
        self, ref: str, hint: EntityType | None = None, server: ServerInfo | None = None
    ) -> Entity:
        """Materialise a placeholder entity for a reference we could not resolve."""
        existing = self.resolve(ref, hint, server)
        if existing is not None:
            return existing
        entity_type = hint or EntityType.INTEGRATION
        cleaned = redact(ref).text
        name = cleaned.replace("\\", "/").rstrip("/").split("/")[-1] or cleaned
        candidate = EntityCandidate(
            entity_type=entity_type,
            name=name,
            qualified_name=cleaned,
            description="Referenced by a discovered artefact but not itself discovered.",
            location=cleaned,
            confidence=Confidence.LOW,
            is_missing=True,
        )
        # ``upsert_entity`` guarantees a placeholder never downgrades a
        # discovered row, so a newly-created placeholder is still is_missing.
        return self.upsert_entity(candidate, server)

    # -- execution servers ------------------------------------------------ #
    @staticmethod
    def _within_bundle(location: str, bundle_dir: str) -> bool:
        if not location or not bundle_dir or not is_local_path(location):
            return False
        try:
            candidate = Path(location).resolve()
            base = Path(bundle_dir).resolve()
        except (OSError, ValueError):
            return False
        return candidate == base or base in candidate.parents

    def _ensure_server(self, server: ServerInfo, source_path: str) -> Entity:
        host = server.hostname.strip()
        cache_key = host.lower()
        cached = self._server_entities.get(cache_key)
        if cached is not None:
            return cached

        ident = (server.fqdn or host).strip()
        candidate = EntityCandidate(
            entity_type=EntityType.SERVER,
            name=host,
            qualified_name=f"server:{ident.lower()}",
            description="Execution server declared by a discovery bundle.",
            location=source_path,
            technology=(server.os or "scheduler host"),
            confidence=Confidence.CONFIRMED,
            source_path=source_path,
            meta={
                "declared": True,
                "fqdn": server.fqdn,
                "os": server.os,
                "environment": server.environment,
            },
        )
        entity = self.upsert_entity(candidate)
        entity.environment = _environment_value(server.environment)
        self._server_entities[cache_key] = entity
        return entity

    def _link_to_server(
        self, entity: Entity, server: ServerInfo, source_path: str
    ) -> None:
        server_entity = self._ensure_server(server, source_path)
        if entity.id == server_entity.id:
            return
        candidate = RelationshipCandidate(
            source_ref=entity.qualified_name,
            target_ref=server_entity.qualified_name,
            relationship_type=RelationshipType.RUNS_ON,
            source_type_hint=EntityType(entity.entity_type),
            target_type_hint=EntityType.SERVER,
            confidence=Confidence.CONFIRMED,
            source_path=source_path,
            snippet=f"{entity.name} runs on {server.hostname}",
            parser="server-bundle",
        )
        self.upsert_relationship(candidate, entity, server_entity, server)

    # -- apply ------------------------------------------------------------ #
    def apply_entities(self, result: ScanResult, server: ServerInfo | None = None) -> None:
        server_path = getattr(server, "source_path", "") if server is not None else ""
        for candidate in result.entities:
            entity = self.upsert_entity(candidate, server)
            if server is not None and (
                candidate.entity_type is EntityType.SCHEDULED_JOB
                or (
                    candidate.entity_type is EntityType.SCRIPT
                    and self._within_bundle(candidate.location, server.bundle_dir)
                )
            ):
                self._link_to_server(entity, server, server_path or candidate.source_path)

        for secret in result.secrets:
            self.session.add(
                SecretEvent(
                    workspace_id=self.workspace.id,
                    source_path=secret.source_path,
                    line_start=secret.line,
                    secret_kind=secret.kind,
                    preview=secret.preview,
                )
            )
            self.stats.secrets_redacted += 1

        self.stats.warnings += len(result.warnings)
        self.session.flush()

    def apply_relationships(self, result: ScanResult, server: ServerInfo | None = None) -> None:
        for candidate in result.relationships:
            source = self.resolve(
                candidate.source_ref, candidate.source_type_hint, server
            ) or self.ensure_missing(
                candidate.source_ref, candidate.source_type_hint or EntityType.SCRIPT, server
            )
            target = self.resolve(
                candidate.target_ref, candidate.target_type_hint, server
            ) or self.ensure_missing(candidate.target_ref, candidate.target_type_hint, server)
            if source.id == target.id:
                self.stats.unmatched_refs += 1
                continue
            self.upsert_relationship(candidate, source, target, server)
        self.session.flush()

    def apply(self, result: ScanResult, server: ServerInfo | None = None) -> None:
        self.apply_entities(result, server)
        self.apply_relationships(result, server)

    def apply_many(
        self,
        results: Iterable[ScanResult] | Iterable[tuple[ScanResult, ServerInfo | None]],
    ) -> NormaliseStats:
        """Apply results in two passes so resolution never depends on file order.

        Every entity from every file is persisted and indexed first; only then
        are relationships resolved. A rescan therefore resolves references to
        exactly the same entities as the original scan.
        """
        items: list[tuple[ScanResult, ServerInfo | None]] = []
        for item in results:
            if isinstance(item, tuple):
                items.append(item)
            else:
                items.append((item, None))
        for result, server in items:
            self.apply_entities(result, server)
        for result, server in items:
            self.apply_relationships(result, server)
        return self.stats

    # -- retirement / reconciliation -------------------------------------- #
    def retire_stale(
        self,
        root: str | Path,
        *,
        parsed_ok_paths: Iterable[str] = (),
    ) -> tuple[int, int]:
        """Retire discoveries under ``root`` that this scan no longer supports.

        A discovery is retired only when *every* piece of evidence that points
        at it comes from the scanned root and that evidence confirms removal:

        * the source file is gone, or
        * the source file was parsed successfully this scan but no longer
          yields the discovery (a dependency was removed from an edited file).

        Files that were skipped, unreadable or made a scanner throw are *not*
        treated as deletions, manual rows are never touched, and anything also
        supported by another root or another piece of evidence survives.
        """
        from sqlalchemy import select

        root_path = Path(str(root)).resolve()
        root_str = str(root_path).replace("\\", "/").rstrip("/")
        ok_paths = {str(p).replace("\\", "/") for p in parsed_ok_paths}

        def under_root(path: str) -> bool:
            normalised = str(path).replace("\\", "/")
            return normalised == root_str or normalised.startswith(root_str + "/")

        def confirms_removal(path: str) -> bool:
            if not under_root(path):
                return False
            candidate = Path(str(path))
            try:
                if candidate.exists():
                    return str(path).replace("\\", "/") in ok_paths
            except OSError:
                return False
            return True

        evidence = list(
            self.session.scalars(
                select(Evidence).where(Evidence.workspace_id == self.workspace.id)
            )
        )
        by_entity: dict[str, list[Evidence]] = defaultdict(list)
        by_rel: dict[str, list[Evidence]] = defaultdict(list)
        for ev in evidence:
            if ev.entity_id:
                by_entity[ev.entity_id].append(ev)
            if ev.relationship_id:
                by_rel[ev.relationship_id].append(ev)

        removed_entities = 0
        for entity in self._by_fingerprint.values():
            if entity.id in self.observed_entity_ids or not entity.is_active:
                continue
            if entity.source_kind == SourceKind.MANUAL.value:
                continue
            evs = by_entity.get(entity.id, [])
            if not evs or not any(under_root(e.source_path) for e in evs):
                continue
            if all(confirms_removal(e.source_path) for e in evs):
                entity.is_active = False
                removed_entities += 1

        removed_relationships = 0
        for rel in self._relationships.values():
            if rel.id in self.observed_relationship_ids or not rel.is_active:
                continue
            if rel.source_kind == SourceKind.MANUAL.value:
                continue
            evs = by_rel.get(rel.id, [])
            if not evs or not any(under_root(e.source_path) for e in evs):
                continue
            if all(confirms_removal(e.source_path) for e in evs):
                rel.is_active = False
                removed_relationships += 1

        self.session.flush()
        self.stats.entities_removed += removed_entities
        self.stats.relationships_removed += removed_relationships
        return removed_entities, removed_relationships
