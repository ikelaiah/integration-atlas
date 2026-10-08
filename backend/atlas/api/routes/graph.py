"""Graph, impact, path-finding and search routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from atlas.api.serialisers import edge_dict, graph_node_dict, node_dict
from atlas.db import get_db
from atlas.domain import Confidence, EntityType, Environment
from atlas.models import Entity, Relationship, Workspace
from atlas.schemas import GraphOut, ImpactOut, PathOut, SearchOut, TraversalOut
from atlas.services.graph import GraphIndex
from atlas.services.impact import analyse_impact, impact_to_dict
from atlas.services.search import search_entities

router = APIRouter(prefix="/api", tags=["graph"])


def _load_index(
    db: Session, workspace_id: str, *, include_rejected: bool = False
) -> GraphIndex:
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    entities = list(db.scalars(select(Entity).where(Entity.workspace_id == workspace_id)))
    relationships = list(
        db.scalars(select(Relationship).where(Relationship.workspace_id == workspace_id))
    )
    return GraphIndex(entities, relationships, include_rejected=include_rejected)


def _filter_index(
    index: GraphIndex,
    *,
    entity_types: list[EntityType] | None,
    min_confidence: Confidence | None,
    environments: list[Environment] | None,
) -> GraphIndex:
    if not entity_types and not min_confidence and not environments:
        return index
    allowed = set(entity_types or [])
    allowed_env = set(environments or [])
    threshold = min_confidence.rank if min_confidence else 0

    keep = {
        eid
        for eid, entity in index.nodes.items()
        if (not allowed or EntityType(entity.entity_type) in allowed)
        and (not allowed_env or Environment(entity.environment) in allowed_env)
        and Confidence(entity.confidence).rank >= threshold
    }
    entities = [e for eid, e in index.nodes.items() if eid in keep]
    relationships = [
        r for r in index.edges if r.source_id in keep and r.target_id in keep
    ]
    return GraphIndex(entities, relationships, include_rejected=index.include_rejected)  # type: ignore[arg-type]


@router.get("/graph", response_model=GraphOut)
def get_graph(
    workspace_id: str = Query(...),
    entity_type: list[EntityType] | None = Query(None),
    min_confidence: Confidence | None = None,
    environment: list[Environment] | None = Query(None),
    include_rejected: bool = False,
    limit: int = Query(2000, le=20000),
    db: Session = Depends(get_db),
) -> GraphOut:
    index = _load_index(db, workspace_id, include_rejected=include_rejected)
    index = _filter_index(
        index,
        entity_types=entity_type,
        min_confidence=min_confidence,
        environments=environment,
    )

    nodes = [
        graph_node_dict(entity, index.degree(eid))
        for eid, entity in sorted(index.nodes.items(), key=lambda kv: kv[1].name.lower())
    ]
    truncated = len(nodes) > limit
    nodes = nodes[:limit]
    kept = {n["id"] for n in nodes}
    edges = [
        edge_dict(edge)
        for edge in index.edges
        if edge.source_id in kept and edge.target_id in kept
    ]

    totals = {
        "nodes": len(nodes),
        "edges": len(edges),
        "total_nodes": len(index.nodes),
        "total_edges": len(index.edges),
    }
    return GraphOut(
        workspace_id=workspace_id,
        nodes=nodes,
        edges=edges,
        truncated=truncated,
        totals=totals,
    )


@router.get("/graph/neighbours/{entity_id}", response_model=TraversalOut)
def get_neighbours(
    entity_id: str,
    workspace_id: str = Query(...),
    db: Session = Depends(get_db),
) -> TraversalOut:
    index = _load_index(db, workspace_id)
    if not index.has(entity_id):
        raise HTTPException(status_code=404, detail="Entity not found")
    result = index.direct_neighbourhood(entity_id)
    return _traversal_out(index, result)


@router.get("/traverse/{entity_id}", response_model=TraversalOut)
def traverse(
    entity_id: str,
    workspace_id: str = Query(...),
    direction: str = Query("downstream", pattern="^(downstream|upstream)$"),
    max_depth: int | None = Query(None, ge=1, le=25),
    db: Session = Depends(get_db),
) -> TraversalOut:
    index = _load_index(db, workspace_id)
    if not index.has(entity_id):
        raise HTTPException(status_code=404, detail="Entity not found")
    result = index.traverse(entity_id, direction=direction, max_depth=max_depth)
    return _traversal_out(index, result)


@router.get("/impact/{entity_id}", response_model=ImpactOut)
def get_impact(
    entity_id: str,
    workspace_id: str = Query(...),
    direction: str = Query("downstream", pattern="^(downstream|upstream)$"),
    max_depth: int | None = Query(None, ge=1, le=25),
    db: Session = Depends(get_db),
) -> ImpactOut:
    index = _load_index(db, workspace_id)
    if not index.has(entity_id):
        raise HTTPException(status_code=404, detail="Entity not found")
    result = analyse_impact(index, entity_id, direction=direction, max_depth=max_depth)
    return ImpactOut(**impact_to_dict(index, result))


@router.get("/path", response_model=PathOut)
def find_path(
    workspace_id: str = Query(...),
    source_id: str = Query(...),
    target_id: str = Query(...),
    db: Session = Depends(get_db),
) -> PathOut:
    index = _load_index(db, workspace_id)
    source = index.nodes.get(source_id)
    target = index.nodes.get(target_id)
    if source is None or target is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    result = index.find_path(source_id, target_id)
    if not result.found:
        return PathOut(
            found=False,
            from_entity=node_dict(source),
            to_entity=node_dict(target),
        )

    steps = []
    for i, eid in enumerate(result.entity_ids):
        steps.append(
            {
                "entity": node_dict(index.nodes[eid]),
                "depth": i,
                "relationship": edge_dict(result.edges[i - 1]) if i > 0 else None,
            }
        )
    return PathOut(
        found=True,
        from_entity=node_dict(source),
        to_entity=node_dict(target),
        steps=steps,
        length=len(result.edges),
    )


@router.get("/search", response_model=SearchOut)
def search(
    workspace_id: str = Query(...),
    q: str = Query(..., min_length=1),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
) -> SearchOut:
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    entities = list(
        db.scalars(
            select(Entity).where(
                Entity.workspace_id == workspace_id, Entity.is_active.is_(True)
            )
        )
    )
    hits = search_entities(entities, q, limit=limit)
    return SearchOut(
        query=q,
        hits=[{"entity": graph_node_dict(h.entity, 0), "score": h.score, "matched_on": h.matched_on} for h in hits],
        total=len(hits),
    )


def _traversal_out(index: GraphIndex, result) -> TraversalOut:
    counts: dict[str, int] = {}
    steps = []
    for step in result.steps:
        entity = index.nodes.get(step.entity_id)
        if entity is None:
            continue
        counts[entity.entity_type] = counts.get(entity.entity_type, 0) + 1
        steps.append(
            {
                "entity": graph_node_dict(entity, index.degree(step.entity_id)),
                "depth": step.depth,
                "relationship": edge_dict(step.edge) if step.edge else None,
            }
        )
    return TraversalOut(
        root=graph_node_dict(index.nodes[result.root_id], index.degree(result.root_id)),
        direction=result.direction,
        steps=steps,
        counts_by_type=counts,
        truncated=result.truncated,
    )
