"""Northstar demo status and reset routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from atlas.db import get_db
from atlas.demo.seeder import demo_status, kept_workspace_name, seed_northstar_demo
from atlas.schemas import DemoResetOut, DemoStatusOut, WorkspaceOut

router = APIRouter(prefix="/api/demo", tags=["demo"])


@router.get("", response_model=DemoStatusOut)
def get_demo_status(db: Session = Depends(get_db)) -> DemoStatusOut:
    """Describe what a reset restores and what it would keep in a separate workspace."""
    status = demo_status(db)
    return DemoStatusOut(
        workspace=WorkspaceOut.model_validate(status.workspace) if status.workspace else None,
        demo_entities=status.demo_entities,
        demo_relationships=status.demo_relationships,
        edited_entities=status.edited_entities,
        reviewed_relationships=status.reviewed_relationships,
        scans=status.scans,
        other_entities=status.other_entities,
        other_relationships=status.other_relationships,
        has_other_data=status.has_other_data,
        kept_workspace_name=kept_workspace_name(db)[0] if status.has_other_data else None,
    )


@router.post("/reset", response_model=DemoResetOut)
def reset_demo(db: Session = Depends(get_db)) -> DemoResetOut:
    """Load or restore the demo without deleting data that came from elsewhere."""
    result = seed_northstar_demo(db, replace=True)
    db.commit()
    return DemoResetOut(status="seeded", **result.as_dict())
