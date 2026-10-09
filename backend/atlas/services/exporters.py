"""Export the discovered model.

Formats:

``json``
    Complete, lossless. Includes evidence. This is the archival format.
``csv``
    Three flat files (entities, relationships, evidence) for spreadsheet users.
``graphml``
    Gephi/yEd/Neo4j-compatible graph. Node/edge attributes carry type,
    confidence and evidence counts.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from sqlalchemy import select
from sqlalchemy.orm import Session

from atlas.models import Entity, Evidence, Relationship, Workspace
from atlas.services.diagrams import DiagramEdge, DiagramNode, render_diagram
from atlas.services.graph import GraphIndex
from atlas.services.redaction import redact, redact_value

SUPPORTED = {"json", "csv", "graphml", "mermaid", "plantuml"}


def _clean(value: object) -> object:
    return redact(value).text if isinstance(value, str) else value


def export_workspace(
    session: Session, workspace: Workspace, output: Path, *, fmt: str = "json"
) -> Path:
    fmt = fmt.lower()
    if fmt not in SUPPORTED:
        raise ValueError(f"Unsupported format '{fmt}'. Choose from {sorted(SUPPORTED)}")

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
    evidence = list(session.scalars(select(Evidence).where(Evidence.workspace_id == workspace.id)))

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    if fmt in {"mermaid", "plantuml"}:
        index = GraphIndex(entities, relationships)
        output.write_text(render_diagram(
            [DiagramNode(e.id, e.name, e.entity_type) for e in index.nodes.values()],
            [DiagramEdge(r.flow_from, r.flow_to, r.relationship_type.value)
             for r in index.edges],
            fmt=fmt,
        ), encoding="utf-8")
    elif fmt == "json":
        _export_json(output, workspace, entities, relationships, evidence)
    elif fmt == "csv":
        _export_csv(output, workspace, entities, relationships, evidence)
    else:
        _export_graphml(output, workspace, entities, relationships, evidence)
    return output


def _export_json(path: Path, workspace, entities, relationships, evidence) -> None:
    payload = {
        "format": "integration-atlas-export",
        "version": 1,
        "workspace": {
            "id": workspace.id,
            "name": workspace.name,
            "slug": workspace.slug,
            "description": workspace.description,
        },
        "entities": [
            {
                "id": e.id,
                "entity_type": e.entity_type,
                "name": _clean(e.name),
                "qualified_name": _clean(e.qualified_name),
                "description": _clean(e.description),
                "owner": _clean(e.owner),
                "environment": e.environment,
                "location": _clean(e.location),
                "technology": _clean(e.technology),
                "confidence": e.confidence,
                "risk_level": e.risk_level,
                "is_missing": e.is_missing,
                "source_kind": e.source_kind,
                "meta": redact_value(e.meta_json or {}, "meta"),
            }
            for e in entities
        ],
        "relationships": [
            {
                "id": r.id,
                "source_id": r.source_id,
                "target_id": r.target_id,
                "relationship_type": r.relationship_type,
                "confidence": r.confidence,
                "source_kind": r.source_kind,
                "review_status": r.review_status,
                "label": _clean(r.label),
            }
            for r in relationships
        ],
        "evidence": [
            {
                "id": ev.id,
                "entity_id": ev.entity_id,
                "relationship_id": ev.relationship_id,
                "evidence_kind": ev.evidence_kind,
                "source_path": _clean(ev.source_path),
                "line_start": ev.line_start,
                "line_end": ev.line_end,
                "snippet": _clean(ev.snippet),
                "parser": ev.parser,
                "confidence": ev.confidence,
            }
            for ev in evidence
        ],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _export_csv(path: Path, workspace, entities, relationships, evidence) -> None:
    stem = path.with_suffix("")
    entity_path = stem.parent / f"{stem.name}-entities.csv"
    rel_path = stem.parent / f"{stem.name}-relationships.csv"
    ev_path = stem.parent / f"{stem.name}-evidence.csv"

    with entity_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            ["id", "type", "name", "qualified_name", "owner", "environment", "location",
             "technology", "confidence", "is_missing"]
        )
        for e in entities:
            writer.writerow(
                [e.id, e.entity_type, _clean(e.name), _clean(e.qualified_name), _clean(e.owner),
                 e.environment, _clean(e.location), _clean(e.technology), e.confidence, e.is_missing]
            )

    with rel_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            ["id", "source_id", "target_id", "relationship_type", "confidence", "review_status", "label"]
        )
        for r in relationships:
            writer.writerow(
                [r.id, r.source_id, r.target_id, r.relationship_type, r.confidence,
                 r.review_status, _clean(r.label)]
            )

    with ev_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            ["id", "entity_id", "relationship_id", "evidence_kind", "source_path",
             "line_start", "line_end", "snippet", "parser", "confidence"]
        )
        for ev in evidence:
            writer.writerow(
                [ev.id, ev.entity_id, ev.relationship_id, ev.evidence_kind, _clean(ev.source_path),
                 ev.line_start, ev.line_end, _clean(ev.snippet), ev.parser, ev.confidence]
            )

    path.write_text(
        f"entities,{entity_path.name}\nrelationships,{rel_path.name}\nevidence,{ev_path.name}\n",
        encoding="utf-8",
    )


def _export_graphml(path: Path, workspace, entities, relationships, evidence) -> None:
    evidence_counts: dict[str, int] = {}
    for ev in evidence:
        if ev.relationship_id:
            evidence_counts[ev.relationship_id] = evidence_counts.get(ev.relationship_id, 0) + 1

    lines: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
        '  <key id="d_name" for="node" attr.name="name" attr.type="string"/>',
        '  <key id="d_type" for="node" attr.name="entity_type" attr.type="string"/>',
        '  <key id="d_qualified" for="node" attr.name="qualified_name" attr.type="string"/>',
        '  <key id="d_tech" for="node" attr.name="technology" attr.type="string"/>',
        '  <key id="d_env" for="node" attr.name="environment" attr.type="string"/>',
        '  <key id="d_conf" for="node" attr.name="confidence" attr.type="string"/>',
        '  <key id="d_owner" for="node" attr.name="owner" attr.type="string"/>',
        '  <key id="d_reltype" for="edge" attr.name="relationship_type" attr.type="string"/>',
        '  <key id="d_relconf" for="edge" attr.name="confidence" attr.type="string"/>',
        '  <key id="d_evid" for="edge" attr.name="evidence_count" attr.type="int"/>',
        f'  <graph id="{escape(workspace.slug)}" edgedefault="directed">',
    ]

    for entity in entities:
        lines.append(f'    <node id={quoteattr(entity.id)}>')
        for key, value in (
            ("d_name", _clean(entity.name)),
            ("d_type", entity.entity_type),
            ("d_qualified", _clean(entity.qualified_name)),
            ("d_tech", _clean(entity.technology)),
            ("d_env", entity.environment),
            ("d_conf", entity.confidence),
            ("d_owner", _clean(entity.owner)),
        ):
            lines.append(f'      <data key="{key}">{escape(str(value or ""))}</data>')
        lines.append("    </node>")

    for index, rel in enumerate(relationships, start=1):
        lines.append(
            f'    <edge id="e{index}" source={quoteattr(rel.source_id)} target={quoteattr(rel.target_id)}>'
        )
        lines.append(f'      <data key="d_reltype">{escape(rel.relationship_type)}</data>')
        lines.append(f'      <data key="d_relconf">{escape(rel.confidence)}</data>')
        lines.append(f'      <data key="d_evid">{evidence_counts.get(rel.id, 0)}</data>')
        lines.append("    </edge>")

    lines.append("  </graph>")
    lines.append("</graphml>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
