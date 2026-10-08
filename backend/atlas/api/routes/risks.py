"""Risk findings routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from atlas.db import get_db
from atlas.demo.seeder import run_risk_analysis
from atlas.models import RiskFinding, Workspace
from atlas.schemas import RiskFindingOut, RiskSummary

router = APIRouter(prefix="/api/risks", tags=["risks"])


@router.get("", response_model=RiskSummary)
def list_risks(
    workspace_id: str = Query(...),
    severity: str | None = None,
    recompute: bool = False,
    db: Session = Depends(get_db),
) -> RiskSummary:
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if recompute:
        run_risk_analysis(db, workspace)
        db.commit()

    stmt = select(RiskFinding).where(RiskFinding.workspace_id == workspace_id)
    rows = list(db.scalars(stmt))
    if severity:
        rows = [r for r in rows if r.severity == severity]

    by_severity: dict[str, int] = {}
    for row in rows:
        by_severity[row.severity] = by_severity.get(row.severity, 0) + 1

    rows.sort(key=lambda r: (-{"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}.get(r.severity, 0), r.title))
    return RiskSummary(
        total=len(rows),
        by_severity=by_severity,
        findings=[RiskFindingOut.model_validate(r) for r in rows],
    )
