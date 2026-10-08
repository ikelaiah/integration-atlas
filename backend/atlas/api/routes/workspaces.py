"""Workspace, overview and demo-seeding routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from atlas.db import get_db
from atlas.demo.seeder import get_or_create_workspace, run_risk_analysis, seed_northstar_demo
from atlas.domain import EntityType
from atlas.models import Entity, Relationship, Workspace
from atlas.schemas import OverviewOut, WorkspaceCreate, WorkspaceOut
from atlas.services.graph import GraphIndex
from atlas.services.risk import RiskContext, run_rules, summarise

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


@router.get("", response_model=list[WorkspaceOut])
def list_workspaces(db: Session = Depends(get_db)) -> list[Workspace]:
    return list(db.scalars(select(Workspace).order_by(Workspace.created_at)))


@router.post("", response_model=WorkspaceOut)
def create_workspace(payload: WorkspaceCreate, db: Session = Depends(get_db)) -> Workspace:
    return get_or_create_workspace(
        db, payload.name, description=payload.description, is_demo=payload.is_demo
    )


@router.get("/{workspace_id}", response_model=WorkspaceOut)
def get_workspace(workspace_id: str, db: Session = Depends(get_db)) -> Workspace:
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


@router.get("/{workspace_id}/overview", response_model=OverviewOut)
def get_overview(workspace_id: str, db: Session = Depends(get_db)) -> OverviewOut:
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
    relationships = list(
        db.scalars(
            select(Relationship).where(
                Relationship.workspace_id == workspace_id,
                Relationship.is_active.is_(True),
            )
        )
    )

    entity_counts: dict[str, int] = {}
    for entity in entities:
        entity_counts[entity.entity_type] = entity_counts.get(entity.entity_type, 0) + 1

    relationship_counts: dict[str, int] = {}
    for rel in relationships:
        relationship_counts[rel.relationship_type] = (
            relationship_counts.get(rel.relationship_type, 0) + 1
        )

    confidence_counts: dict[str, int] = {}
    for entity in entities:
        confidence_counts[entity.confidence] = confidence_counts.get(entity.confidence, 0) + 1
    for rel in relationships:
        confidence_counts[rel.confidence] = confidence_counts.get(rel.confidence, 0) + 1
    total_conf = sum(confidence_counts.values()) or 1
    confidence_pct = {
        key: round(value / total_conf * 100, 1) for key, value in sorted(confidence_counts.items())
    }

    environments: dict[str, int] = {}
    for entity in entities:
        environments[entity.environment] = environments.get(entity.environment, 0) + 1

    index = GraphIndex(entities, relationships)
    drafts = run_rules(RiskContext(index=index, entities=entities))
    risk_summary = summarise(drafts)

    highlights = _build_highlights(entities, relationships, drafts, index)

    totals = {
        "entities": len(entities),
        "relationships": len(relationships),
        "systems": entity_counts.get(EntityType.SYSTEM.value, 0)
        + entity_counts.get(EntityType.APPLICATION.value, 0),
        "databases": entity_counts.get(EntityType.DATABASE.value, 0),
        "jobs": entity_counts.get(EntityType.SCHEDULED_JOB.value, 0),
        "external_services": entity_counts.get(EntityType.EXTERNAL_SERVICE.value, 0),
        "scripts": entity_counts.get(EntityType.SCRIPT.value, 0),
        "files": entity_counts.get(EntityType.FILE.value, 0),
    }

    return OverviewOut(
        workspace=WorkspaceOut.model_validate(workspace),
        entity_counts=entity_counts,
        relationship_counts=relationship_counts,
        totals=totals,
        confidence=confidence_pct,
        environments=environments,
        risk_summary=risk_summary,
        highlights=highlights,
    )


def _build_highlights(entities, relationships, drafts, index: GraphIndex) -> list[str]:
    from atlas.domain import Severity

    lines: list[str] = []
    no_owner = [
        e
        for e in entities
        if e.entity_type in {EntityType.INTEGRATION, EntityType.APPLICATION, EntityType.SYSTEM}
        and not (e.owner or "").strip()
    ]
    if no_owner:
        lines.append(f"{len(no_owner)} integrations have unknown owners")

    missing = [e for e in entities if e.is_missing]
    if missing:
        lines.append(f"{len(missing)} referenced artefacts were never discovered")

    concentration = [d for d in drafts if d.rule_id == "concentration"]
    if concentration:
        worst = max(concentration, key=lambda d: d.details.get("dependents", 0))
        lines.append(worst.title)

    unc = [d for d in drafts if d.rule_id == "unc-path"]
    if unc:
        lines.append(f"{len(unc)} artefacts depend on UNC network paths")

    hardcoded = [d for d in drafts if d.rule_id == "hardcoded-ip"]
    if hardcoded:
        lines.append(f"{len(hardcoded)} artefacts contain hard-coded IP addresses")

    critical = [d for d in drafts if d.severity is Severity.CRITICAL or d.severity is Severity.HIGH]
    if critical:
        lines.append(f"{len(critical)} high-severity risks need review")
    return lines[:8]


@router.post("/{workspace_id}/seed-demo", response_model=dict)
def seed_demo(workspace_id: str | None = None, db: Session = Depends(get_db)) -> dict:
    result = seed_northstar_demo(db, replace=True)
    db.commit()
    return {"status": "seeded", **result.as_dict()}


@router.post("/{workspace_id}/reanalyse-risks", response_model=dict)
def reanalyse(workspace_id: str, db: Session = Depends(get_db)) -> dict:
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    count = run_risk_analysis(db, workspace)
    db.commit()
    return {"workspace_id": workspace_id, "risks": count}
