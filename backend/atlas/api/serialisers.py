"""ORM -> schema conversion helpers shared by the API and CLI."""

from __future__ import annotations

from typing import Any

from atlas.domain import (
    Confidence,
    EntityType,
    Environment,
    RelationshipType,
    ReviewStatus,
    Severity,
    SourceKind,
)
from atlas.models import Entity, Evidence, Relationship
from atlas.services.graph import Edge


def node_dict(entity: Entity) -> dict[str, Any]:
    return {
        "id": entity.id,
        "entity_type": EntityType(entity.entity_type),
        "name": entity.name,
        "qualified_name": entity.qualified_name,
        "display_name": entity.qualified_name or entity.name,
        "technology": entity.technology,
        "environment": Environment(entity.environment),
        "confidence": Confidence(entity.confidence),
        "owner": entity.owner,
        "risk_level": Severity(entity.risk_level) if entity.risk_level else None,
        "is_missing": entity.is_missing,
        "degree": 0,
        "meta_json": entity.meta_json or {},
    }


def graph_node_dict(entity: Entity, degree: int = 0) -> dict[str, Any]:
    data = node_dict(entity)
    data["degree"] = degree
    return data


def edge_dict(edge: Edge) -> dict[str, Any]:
    return {
        "id": edge.id,
        "source_id": edge.source_id,
        "target_id": edge.target_id,
        "relationship_type": edge.relationship_type,
        "flow_from": edge.flow_from,
        "flow_to": edge.flow_to,
        "confidence": Confidence(edge.confidence),
        "review_status": ReviewStatus(edge.review_status),
        "label": edge.label,
    }


def relationship_dict(rel: Relationship) -> dict[str, Any]:
    return {
        "id": rel.id,
        "workspace_id": rel.workspace_id,
        "source_id": rel.source_id,
        "target_id": rel.target_id,
        "relationship_type": RelationshipType(rel.relationship_type),
        "confidence": Confidence(rel.confidence),
        "source_kind": SourceKind(rel.source_kind),
        "review_status": ReviewStatus(rel.review_status),
        "label": rel.label,
        "meta_json": rel.meta_json or {},
        "created_at": rel.created_at,
        "updated_at": rel.updated_at,
    }


def evidence_dict(ev: Evidence) -> dict[str, Any]:
    return {
        "id": ev.id,
        "subject_kind": ev.subject_kind,
        "evidence_kind": ev.evidence_kind,
        "source_path": ev.source_path,
        "line_start": ev.line_start,
        "line_end": ev.line_end,
        "snippet": ev.snippet,
        "parser": ev.parser,
        "confidence": Confidence(ev.confidence),
        "meta_json": ev.meta_json or {},
        "created_at": ev.created_at,
    }
