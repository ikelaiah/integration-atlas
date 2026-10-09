"""Compact scan checkpoints and exact, paged graph comparisons."""

from __future__ import annotations

from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from atlas.models import Entity, Relationship
from atlas.services.redaction import redact

GraphState = dict[str, dict[str, dict[str, Any]]]
Phase = Literal["before", "after"]


def _safe(value: str | None) -> str:
    return redact(value or "").text


def capture_graph(session: Session, workspace_id: str) -> GraphState:
    """Persist only active graph attributes; never evidence or source content."""
    session.flush()
    entities = list(session.scalars(
        select(Entity).where(Entity.workspace_id == workspace_id, Entity.is_active.is_(True))
    ))
    active_ids = {entity.id for entity in entities}
    relationships = list(session.scalars(
        select(Relationship).where(
            Relationship.workspace_id == workspace_id, Relationship.is_active.is_(True)
        )
    ))
    return {
        "entities": {
            entity.id: {
                "entity_type": entity.entity_type,
                "name": _safe(entity.name),
                "qualified_name": _safe(entity.qualified_name),
                "technology": _safe(entity.technology),
                "environment": entity.environment,
                "owner": _safe(entity.owner),
                "confidence": entity.confidence,
                "is_missing": entity.is_missing,
            }
            for entity in entities
        },
        "relationships": {
            relation.id: {
                "source_id": relation.source_id,
                "target_id": relation.target_id,
                "relationship_type": relation.relationship_type,
                "label": _safe(relation.label),
                "confidence": relation.confidence,
                "review_status": relation.review_status,
            }
            for relation in relationships
            if relation.source_id in active_ids and relation.target_id in active_ids
        },
    }


def _name(kind: str, row: dict[str, Any], graph: GraphState) -> str:
    if kind == "entities":
        return str(row["name"])
    names = graph["entities"]
    source = names.get(row["source_id"], {}).get("name", "Unknown entity")
    target = names.get(row["target_id"], {}).get("name", "Unknown entity")
    return f"{source} → {target}"


def _present(kind: str, row: dict[str, Any] | None, graph: GraphState) -> dict[str, Any] | None:
    if row is None:
        return None
    if kind == "entities":
        return row
    names = graph["entities"]
    return {
        **row,
        "source_name": names.get(row["source_id"], {}).get("name", "Unknown entity"),
        "target_name": names.get(row["target_id"], {}).get("name", "Unknown entity"),
    }


def compare_graphs(
    before: GraphState,
    after: GraphState,
    *,
    kind: Literal["entity", "relationship"] | None = None,
    action: Literal["added", "updated", "removed"] | None = None,
    q: str = "",
    offset: int = 0,
    limit: int = 100,
) -> dict[str, Any]:
    """Return exact net totals plus a bounded, searchable change page."""
    counts = {
        key: {"added": 0, "updated": 0, "removed": 0}
        for key in ("entities", "relationships")
    }
    matches: list[dict[str, Any]] = []
    needle = q.strip().casefold()
    for plural in ("entities", "relationships"):
        singular = "entity" if plural == "entities" else "relationship"
        old_rows, new_rows = before[plural], after[plural]
        for row_id in old_rows.keys() | new_rows.keys():
            old, new = old_rows.get(row_id), new_rows.get(row_id)
            if old is None:
                change_action = "added"
            elif new is None:
                change_action = "removed"
            elif old != new:
                change_action = "updated"
            else:
                continue
            counts[plural][change_action] += 1
            if (kind and kind != singular) or (action and action != change_action):
                continue
            shown = new if new is not None else old
            graph = after if new is not None else before
            assert shown is not None
            name = _name(plural, shown, graph)
            old_name = _name(plural, old, before) if old is not None else None
            new_name = _name(plural, new, after) if new is not None else None
            if needle and not any(
                needle in candidate.casefold() for candidate in (old_name, new_name)
                if candidate is not None
            ):
                continue
            matches.append({
                "kind": singular,
                "action": change_action,
                "id": row_id,
                "name": name,
                "type": shown["entity_type" if plural == "entities" else "relationship_type"],
                "changed_fields": sorted(
                    key for key in (old or {}).keys() | (new or {}).keys()
                    if old is not None and new is not None and old.get(key) != new.get(key)
                ),
                "before": _present(plural, old, before),
                "after": _present(plural, new, after),
                "before_name": old_name,
                "after_name": new_name,
            })
    matches.sort(key=lambda item: (item["kind"], item["name"].casefold(), item["id"]))
    page = matches[offset:offset + limit]
    return {
        "counts": counts,
        "total": sum(sum(group.values()) for group in counts.values()),
        "filtered_total": len(matches),
        "changes": page,
        "offset": offset,
        "limit": limit,
        "truncated": offset + len(page) < len(matches),
        "from_counts": {key: len(before[key]) for key in counts},
        "to_counts": {key: len(after[key]) for key in counts},
    }
