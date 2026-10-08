"""PowerShell discovery.

PowerShell is where enterprise integration knowledge goes to hide: one-line
`Invoke-Sqlcmd` calls, UNC paths, and `Export-Csv` to a share that no
runbook mentions. This scanner surfaces that surface area.
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
from atlas.scanners.textutil import collect_constants, expand_variables, join_continuations

_CMDLET_FILE = re.compile(
    r"""(?xi)
    \b(?P<fn>
        Get-Content|Set-Content|Add-Content|Out-File|Import-Csv|Export-Csv|
        Copy-Item|Move-Item|Remove-Item|Rename-Item|Get-ChildItem|New-Item|
        Test-Path|Get-Item|Set-Item
    )
    \b
    (?P<rest>[^\n]{0,300})
    """
)
_PATH_ARG = re.compile(
    r"""(?xi)
    (?:-Path|-LiteralPath|-Destination|-Source|-InputFile|-OutputFile|-FilePath|-TargetPath|-WorkingDirectory)
    \s+
    (?P<q>["']?)(?P<path>(?:[A-Za-z]:\\|\\\\|\.{0,2}[/\\]|/|\$)[^"'\s]*)(?P=q)
    """
)
_QUOTED_PATH = re.compile(
    r"""(?P<q>["'])(?P<path>(?:[A-Za-z]:\\|\\\\|\$)[^"']+|/[\w\-./\\$]{3,200})(?P=q)"""
)

_CMDLET_SQL = re.compile(
    r"""(?xi)
    \b(?P<fn>Invoke-Sqlcmd|sqlcmd|Invoke-DbaQuery|dbatools\w*)
    \b(?P<rest>[^\n]{0,400})
    """
)
_QUERY_ARG = re.compile(r"""(?xi)(?:-Query|-Command|-Q)\s+(?P<q>["'@])(?P<body>.{0,2000}?)(?P=q)""", re.DOTALL)
_INPUTFILE_ARG = re.compile(r"""(?xi)-InputFile\s+(?P<q>["']?)(?P<path>[^"'\s]+)(?P=q)""")
_SERVER_ARG = re.compile(r"""(?xi)(?:-ServerInstance|-Server|-Instance)\s+(?P<q>["']?)(?P<host>[^"'\s;]+)(?P=q)""")
_DB_ARG = re.compile(r"""(?xi)-Database\s+(?P<q>["']?)(?P<db>[^"'\s;]+)(?P=q)""")

_CMDLET_HTTP = re.compile(
    r"""(?xi)
    \b(?P<fn>Invoke-RestMethod|Invoke-WebRequest|curl|wget|RestMethod)
    \b(?P<rest>[^\n]{0,400})
    """
)
_URI_ARG = re.compile(r"""(?xi)(?:-Uri|-Url)\s+(?P<q>["']?)(?P<url>https?://[^"'\s]+)(?P=q)""")

_CMDLET_PROCESS = re.compile(
    r"""(?xi)\b(?P<fn>Start-Process|Start-Job|Start-Sleep|Invoke-Expression|iex)\b(?P<rest>[^\n]{0,300})"""
)
_EXE_ARG = re.compile(r"""(?xi)(?:-FilePath|-Command|-ArgumentList)\s+(?P<q>["']?)(?P<exe>[^"'\s]+\.(?:exe|ps1|bat|cmd|sql))(?P=q)""")

_UNC = re.compile(r"\\\\[A-Za-z0-9._$-]+\\[^\s\"'\)\],;]*")
_URL = re.compile(r"https?://[^\s\"'\)\]>,;]+")
_TABLE_REF = re.compile(
    r"\b(?:FROM|JOIN|INTO|UPDATE|TABLE|EXEC(?:UTE)?)\s+([A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*)",
    re.IGNORECASE,
)

_SIMPLE_NAME = re.compile(r"[^/\\:\s\"']+$")


class PowerShellScanner:
    name = "powershell"
    extensions = frozenset({".ps1", ".psm1", ".psd1", ".ps1xml", ".bat", ".cmd"})

    def can_scan(self, path: Path) -> bool:
        return path.suffix.lower() in self.extensions

    def scan(self, path: Path, text: str) -> ScanResult:
        result = ScanResult()
        rel_path = str(path).replace("\\", "/")
        script_ref = path.name
        is_batch = path.suffix.lower() in {".bat", ".cmd"}

        # PowerShell statements routinely wrap across lines with a backtick.
        # Fold them so each cmdlet is analysed as a whole statement.
        constants = collect_constants(text)
        scanned_text = join_continuations(text)

        result.entities.append(
            EntityCandidate(
                entity_type=EntityType.SCRIPT,
                name=path.name,
                qualified_name=rel_path,
                description="",
                location=rel_path,
                technology="Batch" if is_batch else "PowerShell",
                confidence=Confidence.CONFIRMED,
                source_path=rel_path,
                line=1,
                evidence_kind=EvidenceKind.SOURCE_LINE,
                parser=self.name,
            )
        )

        for lineno, line in iter_lines(scanned_text):
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("REM"):
                continue

            for match in _CMDLET_FILE.finditer(line):
                self._file(result, script_ref, rel_path, lineno, line, match, self.name, constants)

            for match in _CMDLET_SQL.finditer(line):
                self._sql(result, script_ref, rel_path, lineno, line, match, self.name, constants)

            for match in _CMDLET_HTTP.finditer(line):
                self._http(result, script_ref, rel_path, lineno, line, match, self.name)

            if _CMDLET_PROCESS.search(line):
                for exe in _EXE_ARG.finditer(line):
                    result.relationships.append(
                        RelationshipCandidate(
                            source_ref=script_ref,
                            target_ref=expand_variables(exe.group("exe"), constants),
                            relationship_type=RelationshipType.CALLS,
                            target_type_hint=EntityType.SCRIPT,
                            confidence=Confidence.HIGH,
                            source_path=rel_path,
                            line=lineno,
                            snippet=_redact(line),
                            parser=self.name,
                        )
                    )

            for unc in _UNC.finditer(line):
                result.entities.append(
                    EntityCandidate(
                        entity_type=EntityType.FILE,
                        name=_SIMPLE_NAME.search(unc.group(0)).group(0) if _SIMPLE_NAME.search(unc.group(0)) else unc.group(0),
                        qualified_name=unc.group(0),
                        location=unc.group(0),
                        technology="UNC",
                        confidence=Confidence.HIGH,
                        source_path=rel_path,
                        line=lineno,
                        snippet=_redact(line),
                        evidence_kind=EvidenceKind.FILE_PATH,
                        parser=self.name,
                    )
                )
                result.relationships.append(
                    RelationshipCandidate(
                        source_ref=script_ref,
                        target_ref=unc.group(0),
                        relationship_type=RelationshipType.DEPENDS_ON,
                        target_type_hint=EntityType.FILE,
                        confidence=Confidence.HIGH,
                        source_path=rel_path,
                        line=lineno,
                        snippet=_redact(line),
                        evidence_kind=EvidenceKind.FILE_PATH,
                        parser=self.name,
                    )
                )

            if not _CMDLET_HTTP.search(line):
                for url in _URL.finditer(line):
                    self._http_url(result, script_ref, rel_path, lineno, line, url.group(0), self.name)

        return result

    # -- helpers ---------------------------------------------------------- #
    def _file(self, result, script_ref, rel_path, lineno, line, match, parser, constants=None):
        from atlas.scanners.normalise import normalise_path_ref

        rest = match.group("rest")
        path_match = _PATH_ARG.search(rest) or _QUOTED_PATH.search(rest)
        if not path_match:
            return
        raw_path = expand_variables(path_match.group("path"), constants or {})
        if not raw_path or len(raw_path) < 2:
            return
        ref = normalise_path_ref(raw_path)
        fn = match.group("fn")
        is_write = fn in {
            "Set-Content", "Add-Content", "Out-File", "Export-Csv", "Copy-Item",
            "Move-Item", "New-Item", "Rename-Item", "Remove-Item",
        }
        rel_type = RelationshipType.PRODUCES if is_write else RelationshipType.CONSUMES
        if fn in {"Copy-Item", "Move-Item"}:
            rel_type = RelationshipType.TRANSFERS_TO
        etype = EntityType.DIRECTORY if raw_path.endswith(("\\", "/")) else EntityType.FILE
        result.entities.append(
            EntityCandidate(
                entity_type=etype,
                name=_SIMPLE_NAME.search(raw_path.rstrip("\\/")) .group(0) if _SIMPLE_NAME.search(raw_path.rstrip("\\/")) else raw_path,
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

    def _sql(self, result, script_ref, rel_path, lineno, line, match, parser, constants=None):
        rest = expand_variables(match.group("rest"), constants or {})
        query = _QUERY_ARG.search(rest)
        if query:
            body = query.group("body")
            for table_match in _TABLE_REF.finditer(body):
                table = table_match.group(1)
                if table.upper() in {"SELECT", "WHERE", "VALUES", "SET"}:
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

        input_file = _INPUTFILE_ARG.search(rest)
        if input_file:
            ref = input_file.group("path")
            result.entities.append(
                EntityCandidate(
                    entity_type=EntityType.SCRIPT,
                    name=_SIMPLE_NAME.search(ref).group(0) if _SIMPLE_NAME.search(ref) else ref,
                    qualified_name=ref,
                    location=ref,
                    technology="SQL",
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
                    relationship_type=RelationshipType.RUNS,
                    target_type_hint=EntityType.SCRIPT,
                    confidence=Confidence.HIGH,
                    source_path=rel_path,
                    line=lineno,
                    snippet=_redact(line),
                    evidence_kind=EvidenceKind.FILE_PATH,
                    parser=parser,
                )
            )

        server = _SERVER_ARG.search(rest)
        if server:
            host = server.group("host")
            result.entities.append(
                EntityCandidate(
                    entity_type=EntityType.SERVER,
                    name=host,
                    qualified_name=host,
                    location=host,
                    technology="SQL Server",
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
                    target_ref=host,
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

        database = _DB_ARG.search(rest)
        if database:
            db = database.group("db")
            result.entities.append(
                EntityCandidate(
                    entity_type=EntityType.DATABASE,
                    name=db,
                    qualified_name=db,
                    technology="SQL Server",
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
                    target_ref=db,
                    relationship_type=RelationshipType.CONNECTS_TO,
                    target_type_hint=EntityType.DATABASE,
                    confidence=Confidence.HIGH,
                    source_path=rel_path,
                    line=lineno,
                    snippet=_redact(line),
                    evidence_kind=EvidenceKind.CONNECTION_STRING,
                    parser=parser,
                )
            )

    def _http(self, result, script_ref, rel_path, lineno, line, match, parser):
        uri = _URI_ARG.search(match.group("rest"))
        if uri:
            self._http_url(result, script_ref, rel_path, lineno, line, uri.group("url"), parser)

    def _http_url(self, result, script_ref, rel_path, lineno, line, url, parser):
        from atlas.scanners.normalise import host_of

        host = host_of(url)
        result.entities.append(
            EntityCandidate(
                entity_type=EntityType.API,
                name=host or url,
                qualified_name=url,
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


def _redact(value: str) -> str:
    from atlas.services.redaction import redact

    return redact(value).text
