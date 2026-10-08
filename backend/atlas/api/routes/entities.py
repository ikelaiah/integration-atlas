"""Entity, relationship and evidence routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from atlas.db import get_db
from atlas.demo.seeder import fingerprint_entity
from atlas.domain import (
    MANUAL_PROTECTED_FIELDS,
    Confidence,
    EntityType,
    ReviewStatus,
    SourceKind,
    SubjectKind,
)
from atlas.models import Entity, Evidence, Relationship, Workspace
from atlas.schemas import (
    EntityCreate,
    EntityOut,
    EntityUpdate,
    EvidenceIn,
    EvidenceOut,
    RelationshipCreate,
    RelationshipDetail,
    RelationshipOut,
    RelationshipUpdate,
)
from atlas.services.redaction import redact, redact_value

router = APIRouter(prefix="/api", tags=["entities"])


def _workspace_or_404(db: Session, workspace_id: str) -> Workspace:
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


def _entity_or_404(db: Session, entity_id: str) -> Entity:
    entity = db.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    return entity


def _clean(value: str) -> str:
    """Redact a scalar string before it can be persisted."""
    return redact(value).text if isinstance(value, str) else value


@router.get("/entities", response_model=list[EntityOut])
def list_entities(
    workspace_id: str = Query(...),
    entity_type: EntityType | None = None,
    owner: str | None = None,
    environment: str | None = None,
    min_confidence: Confidence | None = None,
    include_missing: bool = True,
    limit: int = Query(2000, le=20000),
    db: Session = Depends(get_db),
) -> list[Entity]:
    _workspace_or_404(db, workspace_id)
    stmt = select(Entity).where(
        Entity.workspace_id == workspace_id, Entity.is_active.is_(True)
    )
    if entity_type is not None:
        stmt = stmt.where(Entity.entity_type == entity_type.value)
    if owner:
        stmt = stmt.where(Entity.owner == owner)
    if environment:
        stmt = stmt.where(Entity.environment == environment)
    if not include_missing:
        stmt = stmt.where(Entity.is_missing.is_(False))
    rows = list(db.scalars(stmt.order_by(Entity.name).limit(limit)))
    if min_confidence is not None:
        threshold = min_confidence.rank
        rows = [r for r in rows if Confidence(r.confidence).rank >= threshold]
    return rows


@router.post("/entities", response_model=EntityOut, status_code=201)
def create_entity(
    workspace_id: str, payload: EntityCreate, db: Session = Depends(get_db)
) -> Entity:
    _workspace_or_404(db, workspace_id)
    qualified_name = _clean(payload.qualified_name or payload.name)
    name = _clean(payload.name)
    location = _clean(payload.location)
    entity = Entity(
        workspace_id=workspace_id,
        entity_type=payload.entity_type.value,
        name=name,
        qualified_name=qualified_name,
        description=_clean(payload.description),
        owner=_clean(payload.owner),
        environment=payload.environment.value,
        location=location,
        technology=_clean(payload.technology),
        confidence=payload.confidence.value,
        source_kind=payload.source_kind.value,
        meta_json=redact_value(payload.meta_json or {}, "meta"),
        fingerprint=fingerprint_entity(
            payload.entity_type.value,
            qualified_name,
            name,
            location,
        ),
    )
    db.add(entity)
    db.flush()
    return entity


@router.get("/entities/{entity_id}", response_model=EntityOut)
def get_entity(entity_id: str, db: Session = Depends(get_db)) -> Entity:
    return _entity_or_404(db, entity_id)


@router.patch("/entities/{entity_id}", response_model=EntityOut)
def update_entity(
    entity_id: str, payload: EntityUpdate, db: Session = Depends(get_db)
) -> Entity:
    entity = _entity_or_404(db, entity_id)
    protected = set(entity.manual_fields_json or [])
    for field_name, value in payload.model_dump(exclude_unset=True).items():
        if field_name == "meta_json":
            value = redact_value(value or {}, "meta")
        elif hasattr(value, "value"):
            value = value.value
        elif isinstance(value, str):
            value = _clean(value)
        setattr(entity, field_name, value)
        if field_name in MANUAL_PROTECTED_FIELDS:
            protected.add(field_name)
    entity.manual_fields_json = sorted(protected)
    # A human edit is manual knowledge: discovery must not undo it.
    if entity.source_kind != SourceKind.MANUAL.value:
        entity.source_kind = SourceKind.MANUAL.value
    db.flush()
    return entity


@router.delete("/entities/{entity_id}", status_code=204)
def delete_entity(entity_id: str, db: Session = Depends(get_db)) -> None:
    entity = _entity_or_404(db, entity_id)
    db.delete(entity)
    db.flush()


@router.get("/entities/{entity_id}/relationships", response_model=list[RelationshipDetail])
def entity_relationships(entity_id: str, db: Session = Depends(get_db)) -> list[dict]:
    entity = _entity_or_404(db, entity_id)
    rows = list(
        db.scalars(
            select(Relationship).where(
                ((Relationship.source_id == entity.id) | (Relationship.target_id == entity.id)),
                Relationship.is_active.is_(True),
            )
        )
    )
    return [_relationship_detail(db, row) for row in rows]


@router.get("/entities/{entity_id}/evidence", response_model=list[EvidenceOut])
def entity_evidence(entity_id: str, db: Session = Depends(get_db)) -> list[Evidence]:
    _entity_or_404(db, entity_id)
    return list(
        db.scalars(select(Evidence).where(Evidence.entity_id == entity_id))
    )


@router.get("/relationships", response_model=list[RelationshipOut])
def list_relationships(
    workspace_id: str = Query(...),
    relationship_type: str | None = None,
    include_rejected: bool = False,
    limit: int = Query(10000, le=50000),
    db: Session = Depends(get_db),
) -> list[Relationship]:
    _workspace_or_404(db, workspace_id)
    stmt = select(Relationship).where(
        Relationship.workspace_id == workspace_id, Relationship.is_active.is_(True)
    )
    if relationship_type:
        stmt = stmt.where(Relationship.relationship_type == relationship_type)
    if not include_rejected:
        stmt = stmt.where(Relationship.review_status != ReviewStatus.REJECTED.value)
    return list(db.scalars(stmt.limit(limit)))


@router.post("/relationships", response_model=RelationshipDetail, status_code=201)
def create_relationship(
    workspace_id: str, payload: RelationshipCreate, db: Session = Depends(get_db)
) -> dict:
    _workspace_or_404(db, workspace_id)
    source = _entity_or_404(db, payload.source_id)
    target = _entity_or_404(db, payload.target_id)
    if source.workspace_id != workspace_id or target.workspace_id != workspace_id:
        raise HTTPException(status_code=400, detail="Entities must belong to the workspace")

    relationship = Relationship(
        workspace_id=workspace_id,
        source_id=source.id,
        target_id=target.id,
        relationship_type=payload.relationship_type.value,
        confidence=payload.confidence.value,
        source_kind=SourceKind.MANUAL.value,
        review_status=ReviewStatus.CONFIRMED.value,
        label=_clean(payload.label),
        meta_json=redact_value(payload.meta_json or {}, "meta"),
        fingerprint=f"{source.id}->{payload.relationship_type.value}->{target.id}|manual",
    )
    db.add(relationship)
    db.flush()

    for ev in payload.evidence:
        db.add(
            Evidence(
                workspace_id=workspace_id,
                relationship_id=relationship.id,
                subject_kind=SubjectKind.RELATIONSHIP.value,
                evidence_kind=ev.evidence_kind.value,
                source_path=_clean(ev.source_path),
                line_start=ev.line_start,
                line_end=ev.line_end,
                snippet=_clean(ev.snippet),
                parser=ev.parser,
                confidence=ev.confidence.value,
                meta_json=redact_value(ev.meta_json or {}, "meta"),
            )
        )
    db.flush()
    return _relationship_detail(db, relationship)


@router.patch("/relationships/{relationship_id}", response_model=RelationshipDetail)
def update_relationship(
    relationship_id: str, payload: RelationshipUpdate, db: Session = Depends(get_db)
) -> dict:
    relationship = db.get(Relationship, relationship_id)
    if relationship is None:
        raise HTTPException(status_code=404, detail="Relationship not found")
    for field_name, value in payload.model_dump(exclude_unset=True).items():
        if hasattr(value, "value"):
            value = value.value
        elif isinstance(value, str):
            value = _clean(value)
        setattr(relationship, field_name, value)
    db.flush()
    return _relationship_detail(db, relationship)


@router.delete("/relationships/{relationship_id}", status_code=204)
def delete_relationship(relationship_id: str, db: Session = Depends(get_db)) -> None:
    relationship = db.get(Relationship, relationship_id)
    if relationship is None:
        raise HTTPException(status_code=404, detail="Relationship not found")
    db.delete(relationship)
    db.flush()


@router.post("/relationships/{relationship_id}/evidence", response_model=EvidenceOut, status_code=201)
def add_evidence(
    relationship_id: str, payload: EvidenceIn, db: Session = Depends(get_db)
) -> Evidence:
    relationship = db.get(Relationship, relationship_id)
    if relationship is None:
        raise HTTPException(status_code=404, detail="Relationship not found")
    evidence = Evidence(
        workspace_id=relationship.workspace_id,
        relationship_id=relationship.id,
        subject_kind=SubjectKind.RELATIONSHIP.value,
        evidence_kind=payload.evidence_kind.value,
        source_path=_clean(payload.source_path),
        line_start=payload.line_start,
        line_end=payload.line_end,
        snippet=_clean(payload.snippet),
        parser=payload.parser,
        confidence=payload.confidence.value,
        meta_json=redact_value(payload.meta_json or {}, "meta"),
    )
    db.add(evidence)
    db.flush()
    return evidence


def _relationship_detail(
    db: Session, relationship: Relationship, evidence_rows: list[Evidence] | None = None
) -> dict:
    source = db.get(Entity, relationship.source_id)
    target = db.get(Entity, relationship.target_id)
    evidence = evidence_rows if evidence_rows is not None else list(
        db.scalars(select(Evidence).where(Evidence.relationship_id == relationship.id))
    )
    from atlas.schemas import EntityOut, RelationshipDetail, RelationshipOut

    return RelationshipDetail(
        **RelationshipOut.model_validate(relationship).model_dump(),
        source=EntityOut.model_validate(source),
        target=EntityOut.model_validate(target),
        evidence=[EvidenceOut.model_validate(e) for e in evidence],
    ).model_dump()
