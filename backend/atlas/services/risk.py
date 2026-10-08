"""Heuristic risk engine.

Every finding carries a human-readable reason and the evidence that produced
it. No opaque scores: a rule fires or it does not, and the user can see why.

Rules are pure functions over the graph so they are unit-testable and easy to
extend. New rules register in :data:`RULES`.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

from atlas.domain import EntityType, Severity
from atlas.models import Entity, RiskFinding
from atlas.services.graph import GraphIndex

_IPV4 = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b")
_UNC = re.compile(r"\\\\[A-Za-z0-9._-]+\\[^\s\"']+")
_URL = re.compile(r"https?://([A-Za-z0-9._-]+)(?::(\d{1,5}))?")
_DEPRECATED_HOST = re.compile(r"(?i)\b(legacy|deprecat|sunset|old[-_]?[a-z0-9]+|v1[-_]?api|sunrise)\b")

#: Ports considered unusual for enterprise automation traffic.
COMMON_PORTS = {80, 443, 1433, 1521, 5432, 3306, 22, 21, 25, 587, 993, 995, 1527, 50000}
#: TLD/hostnames that look like shared infrastructure worth concentration checks.
SERVER_TYPES = {EntityType.SERVER, EntityType.DATABASE, EntityType.EXTERNAL_SERVICE}


@dataclass
class RiskContext:
    index: GraphIndex
    entities: list[Entity]
    evidence_by_entity: dict[str, list[str]] = field(default_factory=dict)
    evidence_by_relationship: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class RiskDraft:
    rule_id: str
    rule_name: str
    severity: Severity
    title: str
    reason: str
    entity_id: str | None = None
    relationship_id: str | None = None
    details: dict = field(default_factory=dict)


Rule = Callable[[RiskContext], list[RiskDraft]]


# --------------------------------------------------------------------------- #
# Rules
# --------------------------------------------------------------------------- #
def rule_hardcoded_credentials(ctx: RiskContext) -> list[RiskDraft]:
    out: list[RiskDraft] = []
    for entity in ctx.entities:
        blobs = [entity.location, entity.description]
        meta = entity.meta_json or {}
        blobs.extend(str(v) for v in meta.values() if isinstance(v, str))
        for blob in blobs:
            if re.search(r"(?i)\b(password|passwd|pwd|api[_-]?key|secret|token)\s*[:=]\s*\S", blob):
                if "<redacted>" in blob:
                    continue
                out.append(
                    RiskDraft(
                        rule_id="hardcoded-credentials",
                        rule_name="Hard-coded credential reference",
                        severity=Severity.HIGH,
                        title=f"{entity.name} references a credential in plain text",
                        reason=(
                            "The entity metadata contains a key/value pair that looks like a "
                            "credential. Secrets must never be stored in source or config."
                        ),
                        entity_id=entity.id,
                    )
                )
                break
    return out


def rule_hardcoded_ips(ctx: RiskContext) -> list[RiskDraft]:
    out: list[RiskDraft] = []
    for entity in ctx.entities:
        blobs = [entity.location, entity.description]
        meta = entity.meta_json or {}
        blobs.extend(str(v) for v in meta.values() if isinstance(v, str))
        ips = {m.group(0) for blob in blobs for m in _IPV4.finditer(blob or "")}
        ips.discard("127.0.0.1")
        ips.discard("0.0.0.0")
        if ips:
            out.append(
                RiskDraft(
                    rule_id="hardcoded-ip",
                    rule_name="Hard-coded IP address",
                    severity=Severity.MEDIUM,
                    title=f"{entity.name} contains hard-coded IP address(es)",
                    reason=(
                        "Hard-coded IP addresses break silently when infrastructure is rebuilt "
                        "or re-addressed. Prefer hostnames or configuration."
                    ),
                    entity_id=entity.id,
                    details={"ips": sorted(ips)},
                )
            )
    return out


def rule_unc_paths(ctx: RiskContext) -> list[RiskDraft]:
    out: list[RiskDraft] = []
    for entity in ctx.entities:
        meta = entity.meta_json or {}
        blobs = [entity.location, entity.description]
        blobs.extend(str(v) for v in meta.values() if isinstance(v, str))
        uncs = {m.group(0) for blob in blobs for m in _UNC.finditer(blob or "")}
        if uncs:
            out.append(
                RiskDraft(
                    rule_id="unc-path",
                    rule_name="UNC network path dependency",
                    severity=Severity.MEDIUM,
                    title=f"{entity.name} depends on a UNC network path",
                    reason=(
                        "UNC paths hide an implicit dependency on a file server and its share "
                        "permissions. These rarely appear in runbooks."
                    ),
                    entity_id=entity.id,
                    details={"paths": sorted(uncs)[:10]},
                )
            )
    return out


def rule_deprecated_hosts(ctx: RiskContext) -> list[RiskDraft]:
    out: list[RiskDraft] = []
    for entity in ctx.entities:
        meta = entity.meta_json or {}
        blobs = [entity.name, entity.location, entity.description]
        blobs.extend(str(v) for v in meta.values() if isinstance(v, str))
        hits = {m.group(0).lower() for blob in blobs for m in _DEPRECATED_HOST.finditer(blob or "")}
        if hits:
            out.append(
                RiskDraft(
                    rule_id="deprecated-host",
                    rule_name="Possible deprecated host or API",
                    severity=Severity.HIGH,
                    title=f"{entity.name} references a possibly deprecated host",
                    reason=(
                        "Name or configuration matches deprecated/legacy naming patterns. "
                        "Confirm this dependency is still supported."
                    ),
                    entity_id=entity.id,
                    details={"matches": sorted(hits)},
                )
            )
    return out


def rule_missing_owner(ctx: RiskContext) -> list[RiskDraft]:
    out: list[RiskDraft] = []
    for entity in ctx.entities:
        if (
            entity.entity_type in {EntityType.INTEGRATION, EntityType.APPLICATION, EntityType.SYSTEM}
            and not (entity.owner or "").strip()
        ):
            out.append(
                    RiskDraft(
                        rule_id="missing-owner",
                        rule_name="Missing owner",
                        severity=Severity.LOW,
                        title=f"{entity.name} has no recorded owner",
                        reason=(
                            "Integrations without an owner are the ones nobody patches during "
                            "an incident."
                        ),
                        entity_id=entity.id,
                    )
                )
    return out


def rule_unknown_dependencies(ctx: RiskContext) -> list[RiskDraft]:
    out: list[RiskDraft] = []
    for entity in ctx.entities:
        if entity.is_missing:
            out.append(
                RiskDraft(
                    rule_id="unknown-dependency",
                    rule_name="Referenced but not discovered",
                    severity=Severity.MEDIUM,
                    title=f"{entity.name} is referenced but was never discovered",
                    reason=(
                        "Something in the estate depends on this entity, but no artefact "
                        "describing it was found during scanning."
                    ),
                    entity_id=entity.id,
                )
            )
    return out


def rule_single_point_of_failure(ctx: RiskContext) -> list[RiskDraft]:
    """Flag infrastructure entities that a large share of integrations depend on."""
    out: list[RiskDraft] = []
    dependents: dict[str, set[str]] = defaultdict(set)
    for edge in ctx.index.edges:
        # Influence flows to the dependent.
        dependents[edge.flow_to].add(edge.flow_from)

    total_integrations = sum(
        1 for e in ctx.entities if e.entity_type in {EntityType.INTEGRATION, EntityType.APPLICATION, EntityType.SCRIPT}
    )
    if total_integrations < 4:
        return out

    for entity in ctx.entities:
        if entity.entity_type not in SERVER_TYPES:
            continue
        count = len(dependents.get(entity.id, ()))
        if count >= max(3, total_integrations // 3):
            out.append(
                RiskDraft(
                    rule_id="concentration",
                    rule_name="Dependency concentration",
                    severity=Severity.HIGH if count >= 8 else Severity.MEDIUM,
                    title=f"{entity.name} is referenced by {count} dependents",
                    reason=(
                        f"{count} entities depend on this one. A change or outage here has an "
                        "outsized blast radius and there is no evident redundancy."
                    ),
                    entity_id=entity.id,
                    details={"dependents": count, "share_of_estate": round(count / total_integrations, 3)},
                )
            )
    return out


def rule_unusual_ports(ctx: RiskContext) -> list[RiskDraft]:
    out: list[RiskDraft] = []
    for entity in ctx.entities:
        meta = entity.meta_json or {}
        blobs = [entity.location, entity.description]
        blobs.extend(str(v) for v in meta.values() if isinstance(v, str))
        ports: set[int] = set()
        for blob in blobs:
            for m in _URL.finditer(blob or ""):
                if m.group(2):
                    ports.add(int(m.group(2)))
            for m in re.finditer(r"(?i)\bport\s*[:=]\s*(\d{2,5})", blob or ""):
                ports.add(int(m.group(1)))
        unusual = sorted(p for p in ports if p not in COMMON_PORTS and p > 0)
        if unusual:
            out.append(
                RiskDraft(
                    rule_id="unusual-port",
                    rule_name="Unusual network port",
                    severity=Severity.LOW,
                    title=f"{entity.name} uses non-standard port(s)",
                    reason=(
                        "Non-standard ports are often undocumented shortcuts. They break when "
                        "firewall baselines are applied."
                    ),
                    entity_id=entity.id,
                    details={"ports": unusual},
                )
            )
    return out


def rule_scheduled_job_missing_script(ctx: RiskContext) -> list[RiskDraft]:
    out: list[RiskDraft] = []
    for entity in ctx.entities:
        if entity.entity_type != EntityType.SCHEDULED_JOB:
            continue
        meta = entity.meta_json or {}
        referenced = meta.get("command") or meta.get("script") or ""
        if not referenced:
            continue
        # A job whose command points at a path nobody owns.
        if str(referenced).startswith(("<", "TODO", "TBD")):
            out.append(
                RiskDraft(
                    rule_id="job-missing-script",
                    rule_name="Scheduled job references missing script",
                    severity=Severity.HIGH,
                    title=f"{entity.name} points at a script that was not discovered",
                    reason=(
                        "The scheduled job's command references an artefact that does not "
                        "appear anywhere in the scanned estate. The job will fail or silently "
                        "do nothing."
                    ),
                    entity_id=entity.id,
                    details={"command": str(referenced)},
                )
            )
    return out


RULES: tuple[Rule, ...] = (
    rule_hardcoded_credentials,
    rule_hardcoded_ips,
    rule_unc_paths,
    rule_deprecated_hosts,
    rule_missing_owner,
    rule_unknown_dependencies,
    rule_single_point_of_failure,
    rule_unusual_ports,
    rule_scheduled_job_missing_script,
)


def run_rules(ctx: RiskContext) -> list[RiskDraft]:
    drafts: list[RiskDraft] = []
    for rule in RULES:
        try:
            drafts.extend(rule(ctx))
        except Exception:  # noqa: BLE001 - a broken rule must not kill the run
            continue
    drafts.sort(key=lambda d: (-d.severity.rank, d.title))
    return drafts


def drafts_to_rows(drafts: list[RiskDraft], workspace_id: str) -> list[RiskFinding]:
    return [
        RiskFinding(
            workspace_id=workspace_id,
            rule_id=d.rule_id,
            rule_name=d.rule_name,
            severity=d.severity.value,
            title=d.title,
            reason=d.reason,
            entity_id=d.entity_id,
            relationship_id=d.relationship_id,
            details_json=d.details,
        )
        for d in drafts
    ]


def summarise(drafts: list[RiskDraft]) -> dict:
    by_severity = Counter(d.severity.value for d in drafts)
    return {
        "total": len(drafts),
        "by_severity": dict(by_severity),
    }
