"""Scan routes.

Real filesystem scanning lives in :mod:`atlas.scanners`. These routes expose it
over HTTP so the UI can drive the same workflow the CLI uses.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from atlas.config import get_settings
from atlas.db import get_db
from atlas.demo.seeder import get_or_create_workspace, run_risk_analysis
from atlas.domain import ScanStatus
from atlas.models import Scan, ScanSnapshot, Workspace
from atlas.schemas import (
    GraphComparisonOut,
    ScanCheckpointOut,
    ScanCreate,
    ScanOut,
    ScanPreview,
    ScanProgress,
)
from atlas.services.history import compare_graphs
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


@router.get("/checkpoints", response_model=list[ScanCheckpointOut])
def list_checkpoints(
    workspace_id: str,
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[ScanCheckpointOut]:
    stmt = (
        select(Scan, ScanSnapshot)
        .join(ScanSnapshot, ScanSnapshot.scan_id == Scan.id)
        .where(Scan.workspace_id == workspace_id, Scan.status == ScanStatus.COMPLETED.value)
        .order_by(Scan.finished_at.desc(), Scan.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return [ScanCheckpointOut(
        scan_id=scan.id, root_path=scan.root_path,
        started_at=_as_utc(scan.started_at), finished_at=_as_utc(scan.finished_at),
        before_counts={key: len(value) for key, value in checkpoint.before_json.items()},
        after_counts={key: len(value) for key, value in checkpoint.after_json.items()},
    ) for scan, checkpoint in db.execute(stmt)]


def _as_utc(stamp: datetime | None) -> datetime | None:
    if stamp is None:
        return None
    return stamp.replace(tzinfo=UTC) if stamp.tzinfo is None else stamp.astimezone(UTC)


def _checkpoint_time(scan: Scan, phase: Literal["before", "after"]) -> datetime:
    stamp = _as_utc(scan.started_at if phase == "before" else scan.finished_at)
    if stamp is None:
        raise HTTPException(status_code=409, detail="Scan checkpoint has no timestamp")
    return stamp


@router.get("/compare", response_model=GraphComparisonOut)
def compare_checkpoints(
    workspace_id: str,
    from_scan_id: str,
    from_phase: Literal["before", "after"],
    to_scan_id: str,
    to_phase: Literal["before", "after"],
    kind: Literal["entity", "relationship"] | None = None,
    action: Literal["added", "updated", "removed"] | None = None,
    q: str = Query("", max_length=200),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> GraphComparisonOut:
    scans = [db.get(Scan, scan_id) for scan_id in (from_scan_id, to_scan_id)]
    if any(scan is None or scan.workspace_id != workspace_id for scan in scans):
        raise HTTPException(status_code=404, detail="Scan not found in workspace")
    from_scan, to_scan = scans
    assert from_scan is not None and to_scan is not None
    if any(scan.status != ScanStatus.COMPLETED.value for scan in scans):
        raise HTTPException(status_code=409, detail="Only completed scans can be compared")
    if _checkpoint_time(from_scan, from_phase) >= _checkpoint_time(to_scan, to_phase):
        raise HTTPException(status_code=400, detail="Choose an earlier and a later checkpoint")
    from_snapshot, to_snapshot = (db.get(ScanSnapshot, scan_id)
                                   for scan_id in (from_scan_id, to_scan_id))
    if from_snapshot is None or to_snapshot is None:
        raise HTTPException(status_code=409, detail="Checkpoint unavailable for an older scan")
    before = from_snapshot.before_json if from_phase == "before" else from_snapshot.after_json
    after = to_snapshot.before_json if to_phase == "before" else to_snapshot.after_json
    result = compare_graphs(
        before, after, kind=kind, action=action, q=q, offset=offset, limit=limit,
    )
    return GraphComparisonOut(
        workspace_id=workspace_id, from_scan_id=from_scan_id, from_phase=from_phase,
        to_scan_id=to_scan_id, to_phase=to_phase, **result,
    )


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
    scan_out = ScanOut.model_validate(scan).model_copy(update={
        "started_at": _as_utc(scan.started_at),
        "finished_at": _as_utc(scan.finished_at),
    })
    return ScanProgress(
        scan=scan_out,
        files_discovered=summary.get("files_discovered", 0),
        files_parsed=summary.get("files_parsed", 0),
        by_extension=summary.get("by_extension", {}),
        entities=summary.get("entities", 0),
        relationships=summary.get("relationships", 0),
        secrets_redacted=summary.get("secrets_redacted", 0),
        warnings=summary.get("warnings", 0),
        events=[e.message for e in (scan.events or [])][:50],
    )
