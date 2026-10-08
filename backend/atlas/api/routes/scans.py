"""Scan routes.

Real filesystem scanning lives in :mod:`atlas.scanners`. These routes expose it
over HTTP so the UI can drive the same workflow the CLI uses.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from atlas.config import get_settings
from atlas.db import get_db
from atlas.demo.seeder import get_or_create_workspace, run_risk_analysis
from atlas.domain import ScanStatus
from atlas.models import Scan, Workspace
from atlas.schemas import ScanCreate, ScanOut, ScanPreview, ScanProgress
from atlas.services.scan_diff import compare, snapshot

router = APIRouter(prefix="/api/scans", tags=["scans"])


@router.get("", response_model=list[ScanProgress])
def list_scans(
    workspace_id: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[ScanProgress]:
    stmt = select(Scan).options(selectinload(Scan.events)).order_by(Scan.started_at.desc()).limit(limit)
    if workspace_id:
        stmt = stmt.where(Scan.workspace_id == workspace_id)
    return [_progress(row) for row in db.scalars(stmt)]


@router.get("/{scan_id}", response_model=ScanProgress)
def get_scan(scan_id: str, db: Session = Depends(get_db)) -> ScanProgress:
    scan = db.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="Scan not found")
    return _progress(scan)


def _validated_root(payload: ScanCreate) -> Path:
    root = Path(payload.root_path).expanduser().resolve()
    settings = get_settings()

    if not root.exists():
        raise HTTPException(status_code=400, detail=f"Path does not exist: {root}")
    if not root.is_dir():
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {root}")
    if settings.scan_root_allowlist:
        allowed = [p.expanduser().resolve() for p in settings.scan_root_allowlist]
        if not any(root == a or root.is_relative_to(a) for a in allowed):
            raise HTTPException(
                status_code=403,
                detail="Scan root is outside the configured allowlist",
            )

    return root


@router.post("/preview", response_model=ScanPreview)
def preview_scan(payload: ScanCreate, db: Session = Depends(get_db)) -> ScanPreview:
    if not payload.workspace_id:
        raise HTTPException(status_code=400, detail="Preview requires an existing workspace_id")
    root = _validated_root(payload)
    workspace = db.get(Workspace, payload.workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    before = snapshot(db, workspace.id)
    from atlas.scanners.runner import run_scan as run_discovery

    savepoint = db.begin_nested()
    try:
        summary = run_discovery(db, workspace, root)
        after = snapshot(db, workspace.id)
        diff = compare(before, after)
    finally:
        savepoint.rollback()
        db.expire_all()
    return ScanPreview(scanner_summary=summary, diff_summary=diff)


@router.post("", response_model=ScanProgress, status_code=201)
def run_scan(payload: ScanCreate, db: Session = Depends(get_db)) -> ScanProgress:
    if not payload.apply_changes:
        raise HTTPException(status_code=400, detail="Use /api/scans/preview for a dry run")
    root = _validated_root(payload)

    if payload.workspace_id:
        workspace = db.get(Workspace, payload.workspace_id)
        if workspace is None:
            raise HTTPException(status_code=404, detail="Workspace not found")
    else:
        workspace = get_or_create_workspace(
            db,
            payload.workspace_name or root.name,
            description=f"Discovered from {root}",
        )

    before = snapshot(db, workspace.id)
    scan = Scan(
        workspace_id=workspace.id,
        root_path=str(root),
        status=ScanStatus.RUNNING.value,
        started_at=datetime.now(UTC),
    )
    db.add(scan)
    db.flush()

    from atlas.scanners.runner import run_scan as run_discovery

    try:
        summary = run_discovery(db, workspace, root, scan=scan)
        scan.diff_summary = compare(before, snapshot(db, workspace.id))
        scan.status = ScanStatus.COMPLETED.value
        scan.scanner_summary = summary
        run_risk_analysis(db, workspace)
    except Exception as exc:  # noqa: BLE001 - surfaced to the operator
        scan.status = ScanStatus.FAILED.value
        scan.error = str(exc)[:2000]
        raise HTTPException(status_code=500, detail=f"Scan failed: {exc}") from exc
    finally:
        scan.finished_at = datetime.now(UTC)
        db.flush()

    return _progress(scan)


def _progress(scan: Scan) -> ScanProgress:
    summary = scan.scanner_summary or {}
    return ScanProgress(
        scan=ScanOut.model_validate(scan),
        files_discovered=summary.get("files_discovered", 0),
        files_parsed=summary.get("files_parsed", 0),
        by_extension=summary.get("by_extension", {}),
        entities=summary.get("entities", 0),
        relationships=summary.get("relationships", 0),
        secrets_redacted=summary.get("secrets_redacted", 0),
        warnings=summary.get("warnings", 0),
        events=[e.message for e in (scan.events or [])][:50],
    )
