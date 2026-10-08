"""SQL discovery.

Practical, not perfect. Extracts schemas, tables, columns where they are
unambiguous, and the DML verbs that say whether data is read or written.
Supports SQL Server, PostgreSQL, DB2 and generic SQL through one tolerant
grammar; dialect-specific quirks are handled with small targeted patterns
rather than a full parser.
"""

from __future__ import annotations

import re
from pathlib import Path

from atlas.domain import (
    Confidence,
    EntityType,
    EvidenceKind,
    RelationshipType,
)
from atlas.scanners.base import (
    EntityCandidate,
    RelationshipCandidate,
    ScanResult,
)

_COMMENT_LINE = re.compile(r"--[^\n]*")
_COMMENT_BLOCK = re.compile(r"/\*.*?\*/", re.DOTALL)
_STRING = re.compile(r"'(?:[^']|'')*'")

_TABLE_TARGET = re.compile(
    r"""(?xi)
    \b(?P<verb>FROM|JOIN|INTO|UPDATE|TABLE|VIEW|PROCEDURE|EXEC(?:UTE)?|MERGE|BULK\s+INSERT)
    \s+
    (?P<name>(?:\[[^\]]+\]|"[^"]+"|[A-Za-z_][\w$#]*)(?:\s*\.\s*(?:\[[^\]]+\]|"[^"]+"|[A-Za-z_][\w$#]*)){0,3})
    """
)
_DML_VERB = re.compile(r"^\s*(?P<verb>SELECT|INSERT|UPDATE|DELETE|MERGE|EXEC(?:UTE)?|TRUNCATE|WITH)\b", re.IGNORECASE)
_COLUMN_ALIAS = re.compile(r"\b([A-Za-z_][\w$#]*)\s*\.\s*([A-Za-z_][\w$#]*)\b")
_CREATE = re.compile(r"(?i)\bCREATE\s+(?:OR\s+REPLACE\s+)?(?P<kind>TABLE|VIEW|PROCEDURE|FUNCTION|SCHEMA|INDEX)\s+(?P<name>[\w.\[\]\"#$]+)")

_INSERT_COLS = re.compile(r"(?is)INSERT\s+INTO\s+[\w.\[\]\"#$]+\s*\((?P<cols>[^)]+)\)")
_SELECT_COLS = re.compile(
    r"(?is)^\s*SELECT\s+(?:DISTINCT\s+)?(?P<cols>.*?)\s+FROM\s",
    re.DOTALL,
)

_SCHEMA_QUALIFIER = re.compile(r"^([\w\[\]\"#$]+)\s*\.\s*([\w\[\]\"#$]+)(?:\s*\.\s*([\w\[\]\"#$]+))?$")


class SqlScanner:
    name = "sql"
    extensions = frozenset({".sql", ".ddl", ".dml", ".psql", ".db2"})

    def can_scan(self, path: Path) -> bool:
        return path.suffix.lower() in self.extensions

    def scan(self, path: Path, text: str) -> ScanResult:
        result = ScanResult()
        rel_path = str(path).replace("\\", "/")
        script_ref = path.name

        result.entities.append(
            EntityCandidate(
                entity_type=EntityType.SCRIPT,
                name=path.name,
                qualified_name=rel_path,
                description=_leading_comment(text),
                location=rel_path,
                technology="SQL",
                confidence=Confidence.CONFIRMED,
                source_path=rel_path,
                line=1,
                evidence_kind=EvidenceKind.SOURCE_LINE,
                parser=self.name,
            )
        )

        cleaned = _COMMENT_BLOCK.sub(lambda m: "\n" * m.group(0).count("\n"), text)
        cleaned = _COMMENT_LINE.sub("", cleaned)

        # Statements: split on semicolons while tracking line numbers.
        for stmt, start_line, _end_line in _iter_statements(cleaned):
            if not stmt.strip():
                continue
            verb_match = _DML_VERB.match(stmt)
            verb = (verb_match.group("verb").upper() if verb_match else "SELECT")
            writes = verb in {"INSERT", "UPDATE", "DELETE", "MERGE", "TRUNCATE"}

            snippet = _redact(_squash(stmt)[:400])

            for match in _CREATE.finditer(stmt):
                kind = match.group("kind").upper()
                raw_name = match.group("name").strip("[]\"")
                etype = {
                    "TABLE": EntityType.TABLE,
                    "VIEW": EntityType.TABLE,
                    "SCHEMA": EntityType.SCHEMA,
                }.get(kind, EntityType.SCRIPT)
                result.entities.append(
                    EntityCandidate(
                        entity_type=etype,
                        name=raw_name.split(".")[-1],
                        qualified_name=raw_name,
                        technology="SQL",
                        confidence=Confidence.CONFIRMED,
                        source_path=rel_path,
                        line=start_line,
                        snippet=snippet,
                        evidence_kind=EvidenceKind.SQL_STATEMENT,
                        parser=self.name,
                    )
                )

            seen_tables: set[str] = set()
            statement_is_delete = verb == "DELETE"
            for index, match in enumerate(_TABLE_TARGET.finditer(stmt)):
                raw = re.sub(r"\s+", "", match.group("name")).strip("[]\"")
                if not raw or raw.upper() in {"SELECT", "VALUES", "SET", "THE", "A", "AS"}:
                    continue
                if raw in seen_tables and match.group("verb").upper() == "FROM":
                    continue
                seen_tables.add(raw)

                parts = raw.split(".")
                name = parts[-1]
                qualified = ".".join(parts[-2:]) if len(parts) >= 2 else raw

                # Schema / database parents.
                if len(parts) >= 2:
                    schema_name = parts[-2]
                    result.entities.append(
                        EntityCandidate(
                            entity_type=EntityType.SCHEMA,
                            name=schema_name,
                            qualified_name=schema_name,
                            technology="SQL",
                            confidence=Confidence.HIGH,
                            source_path=rel_path,
                            line=start_line,
                            snippet=snippet,
                            evidence_kind=EvidenceKind.SQL_STATEMENT,
                            parser=self.name,
                        )
                    )
                    result.relationships.append(
                        RelationshipCandidate(
                            source_ref=qualified,
                            target_ref=schema_name,
                            relationship_type=RelationshipType.DEPENDS_ON,
                            source_type_hint=EntityType.TABLE,
                            target_type_hint=EntityType.SCHEMA,
                            confidence=Confidence.HIGH,
                            source_path=rel_path,
                            line=start_line,
                            snippet=snippet,
                            evidence_kind=EvidenceKind.SQL_STATEMENT,
                            parser=self.name,
                        )
                    )

                result.entities.append(
                    EntityCandidate(
                        entity_type=EntityType.TABLE,
                        name=name,
                        qualified_name=qualified,
                        technology="SQL",
                        confidence=Confidence.CONFIRMED,
                        source_path=rel_path,
                        line=start_line,
                        snippet=snippet,
                        evidence_kind=EvidenceKind.SQL_STATEMENT,
                        parser=self.name,
                    )
                )

                # Classify per *clause*, not per statement. An
                # `INSERT INTO a SELECT ... FROM b` writes a and reads b.
                clause = match.group("verb").upper().replace("  ", " ")
                if clause in {"INTO", "UPDATE", "TABLE", "MERGE", "BULK INSERT"}:
                    rel_type = RelationshipType.WRITES_TO
                elif clause in {"EXEC", "EXECUTE"}:
                    rel_type = RelationshipType.CALLS
                elif statement_is_delete and index == 0:
                    rel_type = RelationshipType.WRITES_TO
                else:
                    rel_type = RelationshipType.READS_FROM

                result.relationships.append(
                    RelationshipCandidate(
                        source_ref=script_ref,
                        target_ref=qualified,
                        relationship_type=rel_type,
                        target_type_hint=EntityType.TABLE,
                        confidence=Confidence.HIGH,
                        source_path=rel_path,
                        line=start_line,
                        snippet=snippet,
                        evidence_kind=EvidenceKind.SQL_STATEMENT,
                        parser=self.name,
                    )
                )

            self._columns(result, script_ref, rel_path, start_line, stmt, snippet, writes)

        return result

    def _columns(self, result, script_ref, rel_path, lineno, stmt, snippet, writes) -> None:
        cols: list[tuple[str, str]] = []

        insert = _INSERT_COLS.search(stmt)
        if insert:
            for raw in insert.group("cols").split(","):
                clean = raw.strip().strip("[]\"")
                if clean and re.fullmatch(r"[A-Za-z_][\w$#]*", clean):
                    cols.append(("", clean))

        select = _SELECT_COLS.match(stmt)
        if select:
            body = select.group("cols")
            for part in body.split(","):
                part = part.strip()
                if not part or part == "*":
                    continue
                alias = _COLUMN_ALIAS.search(part)
                if alias:
                    cols.append((alias.group(1), alias.group(2)))
                else:
                    token = re.match(r"([A-Za-z_][\w$#]*)", part)
                    if token:
                        cols.append(("", token.group(1)))

        seen: set[str] = set()
        for owner, name in cols:
            key = f"{owner}.{name}".lower()
            if key in seen:
                continue
            seen.add(key)
            qualified = f"{owner}.{name}" if owner else name
            result.entities.append(
                EntityCandidate(
                    entity_type=EntityType.COLUMN,
                    name=name,
                    qualified_name=qualified,
                    technology="SQL",
                    confidence=Confidence.HIGH if owner else Confidence.MEDIUM,
                    source_path=rel_path,
                    line=lineno,
                    snippet=snippet,
                    evidence_kind=EvidenceKind.SQL_STATEMENT,
                    parser=self.name,
                )
            )
            result.relationships.append(
                RelationshipCandidate(
                    source_ref=script_ref,
                    target_ref=qualified,
                    relationship_type=RelationshipType.USES_COLUMN,
                    target_type_hint=EntityType.COLUMN,
                    confidence=Confidence.HIGH if owner else Confidence.MEDIUM,
                    source_path=rel_path,
                    line=lineno,
                    snippet=snippet,
                    evidence_kind=EvidenceKind.SQL_STATEMENT,
                    parser=self.name,
                )
            )


def _iter_statements(text: str):
    """Yield (statement, start_line, end_line), tolerating strings and comments."""
    buffer: list[str] = []
    line_no = 1
    start = 1
    in_string = False
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\n":
            line_no += 1
            buffer.append(ch)
            i += 1
            continue
        if not in_string and text.startswith("--", i):
            while i < n and text[i] != "\n":
                i += 1
            continue
        if not in_string and text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end == -1:
                break
            line_no += text.count("\n", i, end + 2)
            i = end + 2
            continue
        if ch == "'":
            in_string = not in_string
            buffer.append(ch)
            i += 1
            continue
        if ch == ";" and not in_string:
            stmt = "".join(buffer)
            yield stmt, start, line_no
            buffer = []
            start = line_no
            i += 1
            continue
        buffer.append(ch)
        i += 1
    if buffer:
        yield "".join(buffer), start, line_no


def _squash(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _leading_comment(text: str) -> str:
    for line in text.splitlines()[:6]:
        stripped = line.strip()
        if stripped.startswith("--"):
            return stripped.lstrip("- ").strip()
    return ""


def _redact(value: str) -> str:
    from atlas.services.redaction import redact

    return redact(value).text
