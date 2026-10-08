"""Evidence-backed relationship review queue."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from atlas.api.routes.entities import _relationship_detail
from atlas.db import get_db
from atlas.domain import Confidence, EvidenceKind, ReviewStatus, SubjectKind
from atlas.models import Evidence, Relationship, Workspace
from atlas.schemas import RelationshipDetail
from atlas.services.redaction import redact

router = APIRouter(prefix="/api/review", tags=["review"])


class ReviewPage(BaseModel):
    items: list[RelationshipDetail]
    total: int
    limit: int
    offset: int


class ReviewDecision(BaseModel):
    review_status: ReviewStatus
    note: str = Field(default="", max_length=5000)


@router.get("", response_model=ReviewPage)
def list_review(
    workspace_id: str = Query(...),
    status: ReviewStatus | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> ReviewPage:
    if db.get(Workspace, workspace_id) is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    predicate = [Relationship.workspace_id == workspace_id, Relationship.is_active.is_(True)]
    if status is not None:
        predicate.append(Relationship.review_status == status.value)
    total = db.scalar(select(func.count()).select_from(Relationship).where(*predicate)) or 0
    has_evidence = select(Evidence.id).where(Evidence.relationship_id == Relationship.id).exists()
    rows = list(db.scalars(
        select(Relationship).where(*predicate)
        .order_by(has_evidence.desc(), Relationship.updated_at.desc(), Relationship.id)
        .options(selectinload(Relationship.source), selectinload(Relationship.target))
        .limit(limit).offset(offset)
    ))
    evidence_by_relationship: dict[str, list[Evidence]] = {row.id: [] for row in rows}
    if rows:
        for evidence in db.scalars(
            select(Evidence).where(Evidence.relationship_id.in_(evidence_by_relationship))
        ):
            evidence_by_relationship[evidence.relationship_id].append(evidence)
    return ReviewPage(
        items=[RelationshipDetail.model_validate(
            _relationship_detail(db, row, evidence_by_relationship[row.id])
        ) for row in rows],
        total=total, limit=limit, offset=offset,
    )


@router.post("/{relationship_id}", response_model=RelationshipDetail)
def decide_review(
    relationship_id: str, payload: ReviewDecision, db: Session = Depends(get_db)
) -> dict:
    row = db.get(Relationship, relationship_id)
    if row is None or not row.is_active:
        raise HTTPException(status_code=404, detail="Active relationship not found")
    row.review_status = payload.review_status.value
    note = redact(payload.note.strip()).text
    if note:
        db.add(Evidence(
            workspace_id=row.workspace_id,
            relationship_id=row.id,
            subject_kind=SubjectKind.RELATIONSHIP.value,
            evidence_kind=EvidenceKind.MANUAL_NOTE.value,
            snippet=note,
            parser="operator",
            confidence=Confidence.MANUAL.value,
        ))
    db.flush()
    return _relationship_detail(db, row)
