"""Python discovery.

Looks for the integration surface of a Python script without importing or
executing it: embedded SQL, HTTP calls, filesystem IO, subprocess spawns,
database drivers and environment variable reads. All matching is
regex/token-based — deliberately. A full Python AST walk is more precise but
brings format-preserving complexity for modest gain at this level of detail;
the line/snippet evidence is what matters to the operator.
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
    iter_lines,
)
from atlas.scanners.textutil import collect_constants, expand_variables

# --- HTTP --------------------------------------------------------------- #
_HTTP_CALL = re.compile(
    r"""(?x)
    (?P<fn>requests|httpx|urllib|urllib3|aiohttp|http\.client)
    \s*\.\s*
    (?P<verb>get|post|put|patch|delete|head|request|urlopen)
    \s*\(\s*
    (?P<arg>
        (?P<q>["'])(?P<url>https?://[^"']+)(?P=q)
      | f(?P<q2>["'])(?P<urlf>https?://[^"']*)(?P=q2)
    )
    """
)
_URL_IN_TEXT = re.compile(r"https?://[^\s\"'\)\]>,;]+")

# --- SQL ---------------------------------------------------------------- #
_SQL_KEYWORDS = r"\b(SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM|MERGE|EXEC(?:UTE)?|CREATE\s+(?:TABLE|VIEW|PROCEDURE|INDEX)|ALTER\s+TABLE|DROP\s+TABLE|TRUNCATE|WITH\s+\w+\s+AS)\b"
_SQL_STRING = re.compile(
    r"""(?P<q>["'])(?P<body>(?:(?!\1).)*?KEYWORDS(?:(?!\1).)*?)(?P=q)""".replace(
        "KEYWORDS", _SQL_KEYWORDS
    ),
    re.IGNORECASE | re.DOTALL,
)
# Triple-quoted literals are where multi-line SQL actually lives.
_SQL_TRIPLE = re.compile(
    r"""(?P<q>\"\"\"|''')(?P<body>.*?KEYWORDS.*?)(?P=q)""".replace(
        "KEYWORDS", _SQL_KEYWORDS
    ),
    re.IGNORECASE | re.DOTALL,
)
_TABLE_REF = re.compile(
    r"\b(?:FROM|JOIN|INTO|UPDATE|TABLE|EXEC(?:UTE)?)\s+([A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*)",
    re.IGNORECASE,
)
_COLUMN_REF = re.compile(r"\b([A-Za-z_][\w]*)\.([A-Za-z_][\w]*)\b")

# --- filesystem --------------------------------------------------------- #
_FILE_IO = re.compile(
    r"""(?x)
    (?P<fn>
        open|read_csv|read_excel|read_json|read_parquet|read_table|
        to_csv|to_excel|to_json|to_parquet|to_sql|read_sql|read_sql_query|
        read_sql_table|to_pickle|read_pickle|os\.path\.join|shutil\.copy|
        shutil\.move|os\.remove|os\.rename|glob\.glob|pathlib\.Path
    )
    \s*\(\s*
    (?P<q>["'])(?P<path>[^"']{2,300})(?P=q)
    """
)

# --- subprocess --------------------------------------------------------- #
_SUBPROCESS = re.compile(
    r"""(?x)
    (?:subprocess|os|commands)
    \s*\.\s*
    (?P<fn>run|call|check_call|check_output|Popen|system|popen|spawnv|execv)
    \s*\(
    """
)
_EXE_CANDIDATE = re.compile(
    r"""(?P<q>["'])(?P<exe>[^"']+\.(?:exe|ps1|bat|cmd|sh|py|sql|cmd))(?P=q)""",
    re.IGNORECASE,
)

# --- database drivers --------------------------------------------------- #
_DB_CONNECT = re.compile(
    r"""(?x)
    (?:create_engine|connect|pyodbc\.connect|psycopg2\.connect|cx_Oracle\.connect|
       sqlite3\.connect|mysql\.connector\.connect|sqlalchemy\.create_engine)
    \s*\(\s*
    (?P<q>["'])(?P<conn>[^"']{3,400})(?P=q)
    """
)
_CONN_HOST = re.compile(
    r"(?i)\b(?:server|host|data\s*source|server\s*instance|address)\s*=\s*([^;\"'\s]+)"
)
_CONN_DB = re.compile(r"(?i)\b(?:database|initial\s*catalog|db)\s*=\s*([^;\"'\s]+)")
_CONN_URL = re.compile(r"(?i)^(?P<scheme>[\w+.-]+)://(?:[^@/]+@)?(?P<host>[^/:?]+)(?:/(?P<db>[^/?#]+))?")

# --- environment -------------------------------------------------------- #
_ENV_REF = re.compile(r"""(?:os\.environ(?:\.get)?|os\.getenv|env\w*)\s*[\(\[]\s*["']([A-Z_][A-Z0-9_]{2,})["']""")

# --- imports worth caring about ---------------------------------------- #
_IMPORT_HINTS = {
    "requests": "http client",
    "httpx": "http client",
    "aiohttp": "http client",
    "pandas": "data frame IO",
    "sqlalchemy": "database",
    "pyodbc": "database",
    "psycopg2": "database",
    "cx_Oracle": "database",
    "pymysql": "database",
    "sqlite3": "database",
    "paramiko": "sftp",
    "pysftp": "sftp",
    "ftplib": "ftp",
    "boto3": "aws",
    "azure": "azure",
    "ldap3": "ldap",
    "smtplib": "email",
    "subprocess": "process",
}
_IMPORT_RE = re.compile(r"^\s*(?:import|from)\s+([A-Za-z_][\w\.]*)", re.MULTILINE)

_NAME_HINT = re.compile(r"/([\w\-]+)\.(?:py|sql)$")


class PythonScanner:
    name = "python"
    extensions = frozenset({".py", ".pyw", ".pyi"})

    def can_scan(self, path: Path) -> bool:
        return path.suffix.lower() in self.extensions

    def scan(self, path: Path, text: str) -> ScanResult:
        result = ScanResult()
        rel_path = str(path).replace("\\", "/")
        constants = collect_constants(text)

        # File-level entity for the script itself.
        result.entities.append(
            EntityCandidate(
                entity_type=EntityType.SCRIPT,
                name=path.name,
                qualified_name=rel_path,
                description=_first_docstring(text),
                location=rel_path,
                technology="Python",
                confidence=Confidence.CONFIRMED,
                source_path=rel_path,
                line=1,
                evidence_kind=EvidenceKind.SOURCE_LINE,
                parser=self.name,
            )
        )
        script_ref = path.name

        # Multi-line SQL lives in triple-quoted literals; scan those once over
        # the whole file so statements are not split across lines.
        for match in _SQL_TRIPLE.finditer(text):
            body = match.group("body")
            line_no = text.count("\n", 0, match.start()) + 1
            self._sql(result, script_ref, rel_path, line_no, body, self.name)

        for lineno, line in iter_lines(text):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            # Substitute known string constants so `read_csv(STUDENT_FILE)`
            # is as visible as `read_csv("/path/students.csv")`.
            expanded = expand_variables(line, constants)

            for match in _HTTP_CALL.finditer(expanded):
                url = match.group("url") or match.group("urlf") or ""
                if not url:
                    continue
                self._http(result, script_ref, rel_path, lineno, line, url, self.name)

            for match in _SQL_STRING.finditer(expanded):
                body = match.group("body")
                self._sql(result, script_ref, rel_path, lineno, body, self.name)

            for match in _FILE_IO.finditer(expanded):
                self._file_io(result, script_ref, rel_path, lineno, line, match, self.name, constants)

            if _SUBPROCESS.search(line):
                for exe in _EXE_CANDIDATE.finditer(line):
                    result.relationships.append(
                        RelationshipCandidate(
                            source_ref=script_ref,
                            target_ref=exe.group("exe"),
                            relationship_type=RelationshipType.CALLS,
                            target_type_hint=EntityType.SCRIPT,
                            confidence=Confidence.HIGH,
                            source_path=rel_path,
                            line=lineno,
                            snippet=_redact(line),
                            evidence_kind=EvidenceKind.SOURCE_LINE,
                            parser=self.name,
                        )
                    )
                result.relationships.append(
                    RelationshipCandidate(
                        source_ref=script_ref,
                        target_ref="subprocess",
                        relationship_type=RelationshipType.CALLS,
                        confidence=Confidence.MEDIUM,
                        source_path=rel_path,
                        line=lineno,
                        snippet=_redact(line),
                        evidence_kind=EvidenceKind.SOURCE_LINE,
                        parser=self.name,
                    )
                )

            for match in _DB_CONNECT.finditer(line):
                self._connection(result, script_ref, rel_path, lineno, line, match.group("conn"), self.name)

            for match in _ENV_REF.finditer(line):
                result.entities.append(
                    EntityCandidate(
                        entity_type=EntityType.INTEGRATION,
                        name=match.group(1),
                        qualified_name=f"env:{match.group(1)}",
                        description="Environment variable referenced by a script.",
                        technology="env",
                        confidence=Confidence.LOW,
                        source_path=rel_path,
                        line=lineno,
                        snippet=_redact(line),
                        evidence_kind=EvidenceKind.CONFIG_KEY,
                        parser=self.name,
                    )
                )

        for match in _IMPORT_RE.finditer(text):
            root = match.group(1).split(".")[0]
            if root in _IMPORT_HINTS:
                result.entities.append(
                    EntityCandidate(
                        entity_type=EntityType.INTEGRATION,
                        name=root,
                        qualified_name=f"library:{root}",
                        description=_IMPORT_HINTS[root],
                        technology=root,
                        confidence=Confidence.LOW,
                        source_path=rel_path,
                        evidence_kind=EvidenceKind.IMPORT,
                        parser=self.name,
                    )
                )

        # A bare URL anywhere else is still worth recording.
        for lineno, line in iter_lines(text):
            if _HTTP_CALL.search(line):
                continue
            for match in _URL_IN_TEXT.finditer(line):
                self._http(result, script_ref, rel_path, lineno, line, match.group(0), self.name)

        return result

    # -- helpers ---------------------------------------------------------- #
    def _http(self, result, script_ref, rel_path, lineno, line, url, parser):
        from atlas.scanners.normalise import host_of

        host = host_of(url)
        result.entities.append(
            EntityCandidate(
                entity_type=EntityType.API,
                name=host or url,
                qualified_name=url,
                description="HTTP endpoint referenced by a script.",
                location=url,
                technology="REST",
                confidence=Confidence.HIGH,
                source_path=rel_path,
                line=lineno,
                snippet=_redact(line),
                evidence_kind=EvidenceKind.URL,
                parser=parser,
            )
        )
        result.relationships.append(
            RelationshipCandidate(
                source_ref=script_ref,
                target_ref=url,
                relationship_type=RelationshipType.CALLS,
                target_type_hint=EntityType.API,
                confidence=Confidence.HIGH,
                source_path=rel_path,
                line=lineno,
                snippet=_redact(line),
                evidence_kind=EvidenceKind.URL,
                parser=parser,
            )
        )

    def _sql(self, result, script_ref, rel_path, lineno, body, parser):
        for table_match in _TABLE_REF.finditer(body):
            table = table_match.group(1)
            if table.upper() in {"SELECT", "WHERE", "VALUES", "SET", "THE", "A"}:
                continue
            parts = table.split(".")
            qualified = ".".join(parts[-2:]) if len(parts) >= 2 else table
            result.entities.append(
                EntityCandidate(
                    entity_type=EntityType.TABLE,
                    name=parts[-1],
                    qualified_name=qualified,
                    technology="SQL",
                    confidence=Confidence.HIGH,
                    source_path=rel_path,
                    line=lineno,
                    snippet=_redact(body[:400]),
                    evidence_kind=EvidenceKind.SQL_STATEMENT,
                    parser=parser,
                )
            )
            verb = body.lstrip().split(None, 1)[0].upper() if body.strip() else "SELECT"
            rel_type = (
                RelationshipType.WRITES_TO
                if verb in {"INSERT", "UPDATE", "DELETE", "MERGE", "TRUNCATE"}
                else RelationshipType.READS_FROM
            )
            result.relationships.append(
                RelationshipCandidate(
                    source_ref=script_ref,
                    target_ref=qualified,
                    relationship_type=rel_type,
                    target_type_hint=EntityType.TABLE,
                    confidence=Confidence.HIGH,
                    source_path=rel_path,
                    line=lineno,
                    snippet=_redact(body[:400]),
                    evidence_kind=EvidenceKind.SQL_STATEMENT,
                    parser=parser,
                )
            )

        for col_match in _COLUMN_REF.finditer(body):
            owner, column = col_match.group(1), col_match.group(2)
            if owner.lower() in {"s", "e", "t", "x", "a", "b"} and column.lower() in {"id"}:
                pass
            result.entities.append(
                EntityCandidate(
                    entity_type=EntityType.COLUMN,
                    name=column,
                    qualified_name=f"{owner}.{column}",
                    technology="SQL",
                    confidence=Confidence.MEDIUM,
                    source_path=rel_path,
                    line=lineno,
                    snippet=_redact(body[:300]),
                    evidence_kind=EvidenceKind.SQL_STATEMENT,
                    parser=parser,
                )
            )
            result.relationships.append(
                RelationshipCandidate(
                    source_ref=script_ref,
                    target_ref=f"{owner}.{column}",
                    relationship_type=RelationshipType.USES_COLUMN,
                    target_type_hint=EntityType.COLUMN,
                    confidence=Confidence.MEDIUM,
                    source_path=rel_path,
                    line=lineno,
                    snippet=_redact(body[:300]),
                    evidence_kind=EvidenceKind.SQL_STATEMENT,
                    parser=parser,
                )
            )

    def _file_io(self, result, script_ref, rel_path, lineno, line, match, parser, constants=None):
        from atlas.scanners.normalise import normalise_path_ref

        raw_path = match.group("path")
        raw_path = expand_variables(raw_path, constants or {})
        if len(raw_path) < 2 or raw_path.startswith(("<", "{", "%")):
            return
        ref = normalise_path_ref(raw_path)
        is_write = match.group("fn") in {
            "to_csv", "to_excel", "to_json", "to_parquet", "to_sql", "to_pickle",
            "shutil.copy", "shutil.move", "os.remove", "os.rename",
        }
        rel_type = RelationshipType.PRODUCES if is_write else RelationshipType.CONSUMES
        etype = EntityType.DIRECTORY if raw_path.endswith(("/", "\\")) else EntityType.FILE
        result.entities.append(
            EntityCandidate(
                entity_type=etype,
                name=raw_path.replace("\\", "/").rstrip("/").split("/")[-1] or raw_path,
                qualified_name=ref,
                location=ref,
                technology="file",
                confidence=Confidence.HIGH,
                source_path=rel_path,
                line=lineno,
                snippet=_redact(line),
                evidence_kind=EvidenceKind.FILE_PATH,
                parser=parser,
            )
        )
        result.relationships.append(
            RelationshipCandidate(
                source_ref=script_ref,
                target_ref=ref,
                relationship_type=rel_type,
                target_type_hint=etype,
                confidence=Confidence.HIGH,
                source_path=rel_path,
                line=lineno,
                snippet=_redact(line),
                evidence_kind=EvidenceKind.FILE_PATH,
                parser=parser,
            )
        )

    def _connection(self, result, script_ref, rel_path, lineno, line, conn, parser):
        from atlas.scanners.normalise import host_of
        from atlas.services.redaction import redact

        cleaned = redact(conn).text
        host = _CONN_HOST.search(conn)
        database = _CONN_DB.search(conn)
        url_match = _CONN_URL.match(conn)
        host_name = (
            (host.group(1) if host else None)
            or (url_match.group("host") if url_match else None)
            or host_of(conn)
        )
        db_name = (
            (database.group(1) if database else None)
            or (url_match.group("db") if url_match else None)
            or ""
        )

        if host_name:
            result.entities.append(
                EntityCandidate(
                    entity_type=EntityType.SERVER,
                    name=host_name,
                    qualified_name=host_name,
                    location=host_name,
                    technology="host",
                    confidence=Confidence.HIGH,
                    source_path=rel_path,
                    line=lineno,
                    snippet=_redact(line),
                    evidence_kind=EvidenceKind.CONNECTION_STRING,
                    parser=parser,
                )
            )
            result.relationships.append(
                RelationshipCandidate(
                    source_ref=script_ref,
                    target_ref=host_name,
                    relationship_type=RelationshipType.CONNECTS_TO,
                    target_type_hint=EntityType.SERVER,
                    confidence=Confidence.HIGH,
                    source_path=rel_path,
                    line=lineno,
                    snippet=_redact(line),
                    evidence_kind=EvidenceKind.CONNECTION_STRING,
                    parser=parser,
                )
            )
        if db_name:
            result.entities.append(
                EntityCandidate(
                    entity_type=EntityType.DATABASE,
                    name=db_name,
                    qualified_name=db_name,
                    technology="database",
                    confidence=Confidence.HIGH,
                    source_path=rel_path,
                    line=lineno,
                    snippet=cleaned,
                    evidence_kind=EvidenceKind.CONNECTION_STRING,
                    parser=parser,
                )
            )
            result.relationships.append(
                RelationshipCandidate(
                    source_ref=script_ref,
                    target_ref=db_name,
                    relationship_type=RelationshipType.CONNECTS_TO,
                    target_type_hint=EntityType.DATABASE,
                    confidence=Confidence.HIGH,
                    source_path=rel_path,
                    line=lineno,
                    snippet=cleaned,
                    evidence_kind=EvidenceKind.CONNECTION_STRING,
                    parser=parser,
                )
            )


def _redact(value: str) -> str:
    from atlas.services.redaction import redact

    return redact(value).text


def _first_docstring(text: str) -> str:
    match = re.search(r'^\s*"""(.{0,300}?)"""', text, re.DOTALL | re.MULTILINE)
    return " ".join(match.group(1).split()) if match else ""
