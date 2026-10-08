"""Compare graph state around a scan without exposing scanned content."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from atlas.models import Entity, Relationship
from atlas.services.redaction import redact

CHANGE_LIMIT = 100


def snapshot(session: Session, workspace_id: str) -> dict[str, dict[str, tuple]]:
    """Capture only durable graph attributes relevant to a scan diff."""
    session.flush()
    entities = list(session.scalars(select(Entity).where(Entity.workspace_id == workspace_id)))
    relationships = list(
        session.scalars(select(Relationship).where(Relationship.workspace_id == workspace_id))
    )
    names = {row.id: row.name for row in entities}
    return {
        "entities": {
            row.id: (
                row.is_active, row.entity_type, row.name, row.qualified_name,
                row.description, row.owner, row.environment, row.location,
                row.technology, row.confidence, row.is_missing, row.source_kind,
                row.meta_json,
            )
            for row in entities
        },
        "relationships": {
            row.id: (
                row.is_active, row.relationship_type,
                names.get(row.source_id, ""), names.get(row.target_id, ""),
                row.label, row.confidence, row.review_status, row.source_kind,
                row.meta_json,
            )
            for row in relationships
        },
    }


def compare(before: dict, after: dict) -> dict:
    counts: dict[str, dict[str, int]] = {}
    changes: list[dict[str, str]] = []
    total = 0
    for kind in ("entities", "relationships"):
        old_rows, new_rows = before[kind], after[kind]
        counts[kind] = {"added": 0, "updated": 0, "removed": 0}
        for row_id in sorted(old_rows.keys() | new_rows.keys()):
            old, new = old_rows.get(row_id), new_rows.get(row_id)
            if new is None or not new[0]:
                action = "removed" if old is not None and old[0] else None
            elif old is None or not old[0]:
                action = "added"
            elif old != new:
                action = "updated"
            else:
                action = None
            if action is None:
                continue
            counts[kind][action] += 1
            total += 1
            if len(changes) >= CHANGE_LIMIT:
                continue
            row = new if action != "removed" else old
            assert row is not None
            changes.append({
                "kind": "entity" if kind == "entities" else "relationship",
                "action": action,
                "id": row_id,
                "type": str(row[1]),
                "name": redact(str(row[2])).text if kind == "entities"
                else redact(f"{row[2]} → {row[3]}").text,
            })
    return {**counts, "total": total, "changes": changes, "truncated": total > len(changes)}
