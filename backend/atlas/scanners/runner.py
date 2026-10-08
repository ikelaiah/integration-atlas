"""Scan orchestration.

Walks a directory tree, hands each candidate file to every scanner that claims
it, and normalises the combined findings into the workspace. This is the same
path the CLI and the HTTP API use, so behaviour is identical everywhere.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from atlas.config import get_settings
from atlas.domain import ScanStatus, SourceKind
from atlas.models import Scan, ScanEvent, Workspace
from atlas.scanners.base import (
    BINARY_EXTENSIONS,
    SKIP_DIRS,
    Scanner,
    ScanResult,
    SecretObservation,
    WarningObservation,
    is_scannable,
    read_text_safe,
)
from atlas.scanners.config_scanner import ConfigScanner
from atlas.scanners.normalise import Normaliser, NormaliseStats
from atlas.scanners.powershell_scanner import PowerShellScanner
from atlas.scanners.python_scanner import PythonScanner
from atlas.scanners.server_bundle import (
    ServerInfo,
    discover_server_bundles,
    server_for_path,
)
from atlas.scanners.sql_scanner import SqlScanner
from atlas.services.redaction import find_secrets, redact


@dataclass
class ScanSummary:
    root_path: str
    files_discovered: int = 0
    files_parsed: int = 0
    by_extension: dict[str, int] = field(default_factory=dict)
    entities: int = 0
    relationships: int = 0
    secrets_redacted: int = 0
    warnings: int = 0
    skipped: int = 0
    errors: int = 0
    normalise: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "root_path": self.root_path,
            "files_discovered": self.files_discovered,
            "files_parsed": self.files_parsed,
            "by_extension": dict(self.by_extension),
            "entities": self.entities,
            "relationships": self.relationships,
            "secrets_redacted": self.secrets_redacted,
            "warnings": self.warnings,
            "skipped": self.skipped,
            "errors": self.errors,
            **self.normalise,
        }


def default_scanners() -> list[Scanner]:
    return [PythonScanner(), PowerShellScanner(), SqlScanner(), ConfigScanner()]


def iter_candidate_files(root: Path, *, max_bytes: int | None = None):
    """Depth-first walk yielding scannable files, skipping noise directories."""
    settings = get_settings()
    limit = max_bytes or settings.max_file_bytes
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir():
                if entry.name.lower() in SKIP_DIRS or entry.name.startswith("."):
                    continue
                stack.append(entry)
                continue
            if entry.suffix.lower() in BINARY_EXTENSIONS:
                continue
            if is_scannable(entry, max_bytes=limit):
                yield entry


def run_scan(
    session: Session,
    workspace: Workspace,
    root: Path,
    *,
    scan: Scan | None = None,
    scanners: list[Scanner] | None = None,
    source_kind: SourceKind = SourceKind.DISCOVERED,
) -> dict:
    """Discover integrations under ``root`` and persist them into ``workspace``.

    Returns a summary dict suitable for a CLI table or an API response.
    """
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError(f"Not a directory: {root}")

    if scan is None:
        scan = Scan(
            workspace_id=workspace.id,
            root_path=str(root),
            status=ScanStatus.RUNNING.value,
            started_at=datetime.now(UTC),
        )
        session.add(scan)
        session.flush()

    plugins = scanners if scanners is not None else default_scanners()
    summary = ScanSummary(root_path=str(root))
    results: list[tuple[ScanResult, ServerInfo | None]] = []
    extension_counts: Counter[str] = Counter()
    parsed_ok_paths: set[str] = set()
    bundles = discover_server_bundles(root)

    for path in iter_candidate_files(root):
        summary.files_discovered += 1
        extension_counts[path.suffix.lower() or path.name.lower()] += 1
        path_str = str(path).replace("\\", "/")
        server = server_for_path(path, bundles)

        claimed = [s for s in plugins if s.can_scan(path)]
        if not claimed:
            summary.skipped += 1
            continue

        text = read_text_safe(path)
        if text is None:
            summary.skipped += 1
            continue

        summary.files_parsed += 1
        file_result = ScanResult()
        file_had_error = False
        file_complete = True

        # Secret detection runs over the whole file regardless of scanner, so
        # nothing sensitive can hide in an artefact no plugin claimed.
        for match in find_secrets(text):
            line_no = text.count("\n", 0, match.start) + 1
            file_result.secrets.append(
                SecretObservation(
                    kind=match.kind,
                    source_path=path_str,
                    line=line_no,
                    preview="<redacted>",
                )
            )

        for plugin in claimed:
            try:
                result = plugin.scan(path, text)
                # Re-redact every string a scanner may have persisted.
                for entity in result.entities:
                    entity.snippet = _redact(entity.snippet)
                    entity.description = _redact(entity.description)
                    entity.location = _redact(entity.location)
                    entity.name = _redact(entity.name)
                    entity.qualified_name = _redact(entity.qualified_name)
                    entity.owner = _redact(entity.owner)
                    entity.technology = _redact(entity.technology)
                    entity.meta = _redact_meta(entity.meta)
                for rel in result.relationships:
                    rel.snippet = _redact(rel.snippet)
                    rel.label = _redact(rel.label)
                    rel.meta = _redact_meta(rel.meta)
                if not result.complete:
                    file_complete = False
                file_result.extend(result)
            except Exception as exc:  # noqa: BLE001 - one bad file must not kill the scan
                summary.errors += 1
                file_had_error = True
                file_result.warnings.append(
                    WarningObservation(
                        message=f"{plugin.name} failed on {path.name}: {exc}",
                        source_path=path_str,
                    )
                )

        if not file_had_error and file_complete:
            parsed_ok_paths.add(path_str)
        results.append((file_result, server))

    summary.by_extension = dict(extension_counts.most_common(24))
    summary.entities = sum(len(r.entities) for r, _ in results)
    summary.relationships = sum(len(r.relationships) for r, _ in results)
    summary.secrets_redacted = sum(len(r.secrets) for r, _ in results)
    summary.warnings = sum(len(r.warnings) for r, _ in results)

    normaliser = Normaliser(session, workspace, source_kind=source_kind)
    stats: NormaliseStats = normaliser.apply_many(results)
    stats.entities_removed, stats.relationships_removed = normaliser.retire_stale(
        root, parsed_ok_paths=parsed_ok_paths
    )
    summary.normalise = stats.as_dict()

    scan.status = ScanStatus.COMPLETED.value
    scan.scanner_summary = summary.as_dict()
    scan.finished_at = datetime.now(UTC)
    session.add(
        ScanEvent(
            scan_id=scan.id,
            kind="summary",
            message=(
                f"{summary.files_parsed} files parsed · "
                f"{stats.entities_added} entities added · "
                f"{stats.relationships_added} relationships added · "
                f"{stats.secrets_redacted} secrets redacted"
            ),
            details_json=summary.as_dict(),
        )
    )
    session.flush()
    return summary.as_dict()


def _redact(value: str) -> str:
    if not value:
        return value
    return redact(value).text if value else value


def _redact_meta(value: dict) -> dict:
    from atlas.services.redaction import redact_value

    cleaned = redact_value(value or {}, "meta")
    return cleaned if isinstance(cleaned, dict) else {}
