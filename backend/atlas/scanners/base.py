"""Scanner plugin contract.

A scanner turns one artefact (a file on disk) into zero or more
:class:`Finding` observations. Scanners know *nothing* about persistence,
entity identity or the database — that is the normaliser's job. This keeps
discovery testable in isolation and makes new language support additive.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from atlas.domain import (
    Confidence,
    EntityType,
    EvidenceKind,
    RelationshipType,
)

#: Files larger than this are skipped rather than partially parsed.
MAX_FILE_BYTES = 4_000_000

#: Directories that are never worth descending into.
SKIP_DIRS = frozenset(
    {
        ".git", ".hg", ".svn", ".venv", "venv", "node_modules", "__pycache__",
        ".tox", ".mypy_cache", ".pytest_cache", "dist", "build", ".idea",
        ".vscode", "target", "bin", "obj",
    }
)

#: Binary extensions that are never worth opening as text.
BINARY_EXTENSIONS = frozenset(
    {
        ".dll", ".exe", ".so", ".dylib", ".bin", ".png", ".jpg", ".jpeg", ".gif",
        ".pdf", ".zip", ".7z", ".gz", ".tar", ".jar", ".class", ".pyc", ".pdb",
        ".woff", ".woff2", ".ttf", ".eot", ".ico", ".mp4", ".mp3", ".db", ".sqlite",
        ".mdb", ".accdb", ".xls", ".xlsx", ".doc", ".docx", ".pptx",
    }
)


@dataclass
class EntityCandidate:
    """An entity observed in an artefact, before identity resolution."""

    entity_type: EntityType
    name: str
    qualified_name: str = ""
    description: str = ""
    location: str = ""
    technology: str = ""
    owner: str = ""
    confidence: Confidence = Confidence.MEDIUM
    is_missing: bool = False
    meta: dict = field(default_factory=dict)
    #: Where this observation came from, used as evidence.
    source_path: str = ""
    line: int | None = None
    snippet: str = ""
    evidence_kind: EvidenceKind = EvidenceKind.SOURCE_LINE
    parser: str = ""


@dataclass
class RelationshipCandidate:
    """A relationship observed in an artefact, before identity resolution.

    ``source_ref`` / ``target_ref`` are *references* — names or qualified
    names the normaliser resolves against the entity set. They are not ids.
    """

    source_ref: str
    target_ref: str
    relationship_type: RelationshipType
    source_type_hint: EntityType | None = None
    target_type_hint: EntityType | None = None
    label: str = ""
    confidence: Confidence = Confidence.MEDIUM
    source_path: str = ""
    line: int | None = None
    snippet: str = ""
    evidence_kind: EvidenceKind = EvidenceKind.SOURCE_LINE
    parser: str = ""
    meta: dict = field(default_factory=dict)


@dataclass
class SecretObservation:
    """A redacted secret, recorded so the operator can see what was masked."""

    kind: str
    source_path: str
    line: int | None = None
    preview: str = ""


@dataclass
class WarningObservation:
    message: str
    source_path: str = ""
    line: int | None = None


@dataclass
class ScanResult:
    """Everything one scanner produced for one file."""

    entities: list[EntityCandidate] = field(default_factory=list)
    relationships: list[RelationshipCandidate] = field(default_factory=list)
    secrets: list[SecretObservation] = field(default_factory=list)
    warnings: list[WarningObservation] = field(default_factory=list)
    #: False when the scanner could not fully parse the artefact (malformed or
    #: truncated JSON/YAML). A partial parse must never authorise retirement of
    #: previous discoveries — see :mod:`atlas.scanners.runner`.
    complete: bool = True

    def extend(self, other: ScanResult) -> None:
        self.entities.extend(other.entities)
        self.relationships.extend(other.relationships)
        self.secrets.extend(other.secrets)
        self.warnings.extend(other.warnings)
        self.complete = self.complete and other.complete

    @property
    def is_empty(self) -> bool:
        return not (self.entities or self.relationships or self.secrets or self.warnings)


@runtime_checkable
class Scanner(Protocol):
    """Protocol implemented by every discovery plugin."""

    #: Human-readable name used in evidence rows ("python", "sql", ...).
    name: str

    #: File extensions this scanner claims, lowercase with the dot.
    extensions: frozenset[str]

    def can_scan(self, path: Path) -> bool:
        """Return True when this scanner understands ``path``."""
        ...

    def scan(self, path: Path, text: str) -> ScanResult:
        """Analyse ``text`` (already read and size-checked) from ``path``."""
        ...


def is_scannable(path: Path, *, max_bytes: int = MAX_FILE_BYTES) -> bool:
    if not path.is_file():
        return False
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return False
    try:
        return path.stat().st_size <= max_bytes
    except OSError:
        return False


def read_text_safe(path: Path, *, max_bytes: int = MAX_FILE_BYTES) -> str | None:
    """Read a file as text, tolerating encodings and malformed content.

    Never raises: a file we cannot read is a warning, not a failed scan.
    """
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if len(raw) > max_bytes:
        return None
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def iter_lines(text: str) -> Iterable[tuple[int, str]]:
    """Yield 1-indexed line numbers and their content."""
    yield from enumerate(text.splitlines(), start=1)
