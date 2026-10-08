"""Configuration and scheduler discovery.

Handles the artefacts that carry integration knowledge but are not code:

* JSON / YAML / XML / INI / ``.env``-style key/value files
* Windows Task Scheduler XML exports
* cron definitions and ``/etc/cron.d`` entries

Values that look like credentials are redacted before anything is recorded.
"""

from __future__ import annotations

import json
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
    SecretObservation,
    WarningObservation,
    iter_lines,
)
from atlas.scanners.server_bundle import MANIFEST_NAME
from atlas.services.redaction import redact

_URL = re.compile(r"https?://[^\s\"'<>)\]},{;]+")
_HOST = re.compile(r"\b(?:host|hostname|server|serverinstance|data\s*source|address)\b\s*[:=]\s*[\"']?([A-Za-z0-9._-]+)", re.IGNORECASE)
_PORT = re.compile(r"\bport\b\s*[:=]\s*[\"']?(\d{2,5})", re.IGNORECASE)
_PATH = re.compile(r"\b(?:path|file|directory|folder|dir|script|command|executable|workingdirectory|inputfile|outputfile)\b\s*[:=]\s*[\"']?([^\s\"'<>]{3,300})", re.IGNORECASE)
_DBNAME = re.compile(r"\b(?:database|db|initial\s*catalog|catalog)\b\s*[:=]\s*[\"']?([A-Za-z0-9_ -]{2,120})", re.IGNORECASE)
_CONN = re.compile(r"(?i)\bconnection[_\-]?string\b\s*[:=]\s*[\"']?([^\"'\n]{4,400})")
_ENV_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$")
_KV_LINE = re.compile(r"^\s*([A-Za-z_][\w\.\-]*)\s*[:=]\s*(.+?)\s*$")

# Windows Task Scheduler
_TASK_NAME = re.compile(r"<URI>([^<]+)</URI>")
_TASK_COMMAND = re.compile(r"<Command>([^<]+)</Command>")
_TASK_ARGS = re.compile(r"<Arguments>([^<]+)</Arguments>")
_TASK_WORKDIR = re.compile(r"<WorkingDirectory>([^<]+)</WorkingDirectory>")
_TASK_START = re.compile(r"<StartBoundary>([^<]+)</StartBoundary>")
_TASK_INTERVAL = re.compile(r"<(?:DaysInterval|WeeksInterval|MinutesInterval)>(\d+)</(?:DaysInterval|WeeksInterval|MinutesInterval)>")
_TASK_USER = re.compile(r"<UserId>([^<]+)</UserId>")
_TASK_ENABLED = re.compile(r"<Enabled>(true|false)</Enabled>", re.IGNORECASE)

# cron
_SCHEDULE = r"(?:\S+\s+){4}\S+|@(?:reboot|yearly|annually|monthly|weekly|daily|hourly)"
# System crontabs (/etc/crontab, /etc/cron.d/*) carry an optional user column:
#   schedule  user  command
_CRON_LINE = re.compile(
    r"""^\s*
    (?P<schedule>(?:\S+\s+){4}\S+|@(?:reboot|yearly|annually|monthly|weekly|daily|hourly))
    \s+
    (?:(?P<user>\w+)\s+)?
    (?P<command>.+)$
    """,
    re.VERBOSE,
)
# User crontabs (spool) have no user column: the file's owner is the user.
#   schedule  command
_CRON_USER_LINE = re.compile(
    r"""^\s*
    (?P<schedule>(?:\S+\s+){4}\S+|@(?:reboot|yearly|annually|monthly|weekly|daily|hourly))
    \s+
    (?P<command>.+)$
    """,
    re.VERBOSE,
)

_EXTENSIONS = frozenset({
    ".json", ".yaml", ".yml", ".xml", ".ini", ".cfg", ".conf", ".config",
    ".env", ".properties", ".toml",
})
_SPECIAL_FILENAMES = frozenset({".env", ".env.example", ".env.sample", "docker-compose.yml", "docker-compose.yaml"})


class ConfigScanner:
    name = "config"
    extensions = _EXTENSIONS | frozenset({""})

    def can_scan(self, path: Path) -> bool:
        name = path.name.lower()
        # The bundle manifest is metadata, handled by the runner, not a config
        # file to mine for entities.
        if name == MANIFEST_NAME:
            return False
        if name in _SPECIAL_FILENAMES or name.startswith(".env"):
            return True
        parts = str(path).lower().replace("\\", "/").split("/")
        if (
            name in {"crontab", "cron.d"}
            or "cron" in name
            or "cron.d" in parts
            or "crontabs" in parts
            or (len(parts) >= 2 and parts[-2] in {"cron", "crontabs"})
        ):
            return True
        return path.suffix.lower() in _EXTENSIONS

    def scan(self, path: Path, text: str) -> ScanResult:
        result = ScanResult()
        rel_path = str(path).replace("\\", "/")
        name = path.name.lower()
        path_lower = str(path).lower().replace("\\", "/")

        if "cron" in path_lower or name == "crontab":
            user_crontab, user = _crontab_context(path_lower, name)
            self._cron(result, rel_path, text, user_crontab=user_crontab, user=user)
        elif name.endswith(".xml") or "task" in path_lower or "scheduler" in path_lower:
            self._task_scheduler(result, rel_path, text)
        else:
            self._generic(result, path, rel_path, text)

        return result

    # -- generic config --------------------------------------------------- #
    def _generic(self, result: ScanResult, path: Path, rel_path: str, text: str) -> None:
        structured: dict | None = None
        suffix = path.suffix.lower()
        try:
            if suffix == ".json":
                structured = json.loads(text)
            elif suffix in {".yaml", ".yml"}:
                import yaml

                structured = yaml.safe_load(text)
        except Exception as exc:  # noqa: BLE001 - malformed config is a warning
            # A malformed/truncated structured file is only partially parsed by
            # the line fallback below, so it must not authorise retirement.
            result.complete = False
            result.warnings.append(
                WarningObservation(message=f"Could not parse {suffix or 'config'}: {exc}", source_path=rel_path)
            )

        if isinstance(structured, dict):
            self._walk_mapping(result, rel_path, structured)
            return

        for lineno, line in iter_lines(text):
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", ";", "//")):
                continue
            self._line(result, rel_path, lineno, line)

    def _walk_mapping(self, result: ScanResult, rel_path: str, data: dict, prefix: str = "") -> None:
        for key, value in data.items():
            qualified = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, dict):
                self._walk_mapping(result, rel_path, value, qualified)
                continue
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        self._walk_mapping(result, rel_path, item, qualified)
                    elif isinstance(item, str):
                        self._value(result, rel_path, qualified, item)
                continue
            self._value(result, rel_path, qualified, value)

    def _line(self, result: ScanResult, rel_path: str, lineno: int, line: str) -> None:
        for match in _URL.finditer(line):
            self._url(result, rel_path, lineno, line, match.group(0))
        for match in _CONN.finditer(line):
            self._connection(result, rel_path, lineno, line, match.group(1))
        for pattern, handler in (
            (_HOST, self._host),
            (_DBNAME, self._database),
            (_PATH, self._path),
        ):
            for match in pattern.finditer(line):
                handler(result, rel_path, lineno, line, match.group(1))
        for match in _PORT.finditer(line):
            self._port(result, rel_path, lineno, line, match.group(1))

        # key=value / key: value lines (INI sections, .env, properties).
        kv = _KV_LINE.match(line.strip()) or _ENV_LINE.match(line.strip())
        if kv:
            key, value = kv.group(1), kv.group(2).strip().strip("\"'")
            self._value(result, rel_path, key, value, lineno, line)

    def _value(
        self,
        result: ScanResult,
        rel_path: str,
        key: str,
        value: object,
        lineno: int | None = None,
        line: str = "",
    ) -> None:
        if not isinstance(value, str):
            return
        cleaned = redact(f"{key}={value}").text
        body = cleaned.split("=", 1)[1] if "=" in cleaned else cleaned
        if _URL.search(body):
            for match in _URL.finditer(body):
                self._url(result, rel_path, lineno, f"{key}={body}", match.group(0))
            return
        lowered = key.lower()
        if any(h in lowered for h in ("host", "server", "address")):
            self._host(result, rel_path, lineno, f"{key}={body}", body.strip("\"'"))
        elif any(h in lowered for h in ("database", "_db", "catalog")):
            self._database(result, rel_path, lineno, f"{key}={body}", body.strip("\"'"))
        elif any(h in lowered for h in ("path", "file", "dir", "folder", "script", "command")):
            self._path(result, rel_path, lineno, f"{key}={body}", body.strip("\"'"))
        elif "port" in lowered:
            self._port(result, rel_path, lineno, f"{key}={body}", body.strip("\"'"))
        elif any(h in lowered for h in ("password", "secret", "token", "key", "credential")):
            result.secrets.append(
                SecretObservation(
                    kind="credential", source_path=rel_path, line=lineno, preview=cleaned[:120]
                )
            )

    # -- specific handlers ------------------------------------------------ #
    def _url(self, result, rel_path, lineno, line, url):
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
                snippet=redact(line).text,
                evidence_kind=EvidenceKind.URL,
                parser=self.name,
            )
        )

    def _connection(self, result, rel_path, lineno, line, conn):
        cleaned = redact(conn).text
        result.entities.append(
            EntityCandidate(
                entity_type=EntityType.DATABASE,
                name=cleaned.split(";")[0][:60],
                qualified_name=cleaned[:300],
                location=cleaned[:300],
                technology="connection string",
                confidence=Confidence.MEDIUM,
                source_path=rel_path,
                line=lineno,
                snippet=cleaned,
                evidence_kind=EvidenceKind.CONNECTION_STRING,
                parser=self.name,
            )
        )

    def _host(self, result, rel_path, lineno, line, value):
        value = value.strip().strip("\"'")
        if not value or len(value) < 2:
            return
        result.entities.append(
            EntityCandidate(
                entity_type=EntityType.SERVER,
                name=value,
                qualified_name=value,
                location=value,
                technology="host",
                confidence=Confidence.MEDIUM,
                source_path=rel_path,
                line=lineno,
                snippet=redact(line).text,
                evidence_kind=EvidenceKind.CONFIG_KEY,
                parser=self.name,
            )
        )

    def _database(self, result, rel_path, lineno, line, value):
        value = value.strip().strip("\"'")
        if not value or len(value) < 2:
            return
        result.entities.append(
            EntityCandidate(
                entity_type=EntityType.DATABASE,
                name=value,
                qualified_name=value,
                technology="database",
                confidence=Confidence.MEDIUM,
                source_path=rel_path,
                line=lineno,
                snippet=redact(line).text,
                evidence_kind=EvidenceKind.CONFIG_KEY,
                parser=self.name,
            )
        )

    def _path(self, result, rel_path, lineno, line, value):
        from atlas.scanners.normalise import normalise_path_ref

        value = value.strip().strip("\"'")
        if len(value) < 3 or value.startswith(("<", "$", "%", "{")):
            return
        ref = normalise_path_ref(value)
        etype = EntityType.DIRECTORY if value.endswith(("/", "\\")) else EntityType.FILE
        result.entities.append(
            EntityCandidate(
                entity_type=etype,
                name=value.replace("\\", "/").rstrip("/").split("/")[-1],
                qualified_name=ref,
                location=ref,
                technology="path",
                confidence=Confidence.MEDIUM,
                source_path=rel_path,
                line=lineno,
                snippet=redact(line).text,
                evidence_kind=EvidenceKind.FILE_PATH,
                parser=self.name,
            )
        )

    def _port(self, result, rel_path, lineno, line, value):
        result.entities.append(
            EntityCandidate(
                entity_type=EntityType.INTEGRATION,
                name=f"port {value}",
                qualified_name=f"port:{value}",
                technology="tcp",
                confidence=Confidence.LOW,
                source_path=rel_path,
                line=lineno,
                snippet=redact(line).text,
                evidence_kind=EvidenceKind.CONFIG_KEY,
                parser=self.name,
            )
        )

    # -- Windows Task Scheduler ------------------------------------------- #
    def _task_scheduler(self, result: ScanResult, rel_path: str, text: str) -> None:
        name_match = _TASK_NAME.search(text)
        command_match = _TASK_COMMAND.search(text)
        args_match = _TASK_ARGS.search(text)
        workdir_match = _TASK_WORKDIR.search(text)
        start_match = _TASK_START.search(text)
        interval_match = _TASK_INTERVAL.search(text)
        user_match = _TASK_USER.search(text)

        # Task Scheduler URIs are rooted (`\group\task-name`). Keep the full
        # path as the identity so same-named tasks in different folders (and on
        # different servers) stay distinct; the leaf is the display name.
        raw_name = name_match.group(1).strip() if name_match else Path(rel_path).stem
        normalised_path = raw_name.replace("\\", "/").strip("/")
        task_path = normalised_path or raw_name
        task_name = normalised_path.split("/")[-1] if normalised_path else raw_name
        command = command_match.group(1).strip() if command_match else ""
        args = args_match.group(1).strip() if args_match else ""

        if not command:
            result.warnings.append(
                WarningObservation(message="Task has no <Command> element", source_path=rel_path)
            )

        schedule_bits = []
        if start_match:
            schedule_bits.append(start_match.group(1))
        if interval_match:
            schedule_bits.append(f"every {interval_match.group(1)}")

        result.entities.append(
            EntityCandidate(
                entity_type=EntityType.SCHEDULED_JOB,
                name=task_name,
                qualified_name=task_path,
                description="Windows scheduled task.",
                location=rel_path,
                technology="Windows Task Scheduler",
                confidence=Confidence.CONFIRMED,
                source_path=rel_path,
                evidence_kind=EvidenceKind.SCHEDULER_ENTRY,
                parser=self.name,
                meta={
                    "command": command,
                    "arguments": args,
                    "working_directory": workdir_match.group(1) if workdir_match else "",
                    "schedule": " ".join(schedule_bits),
                    "run_as": user_match.group(1) if user_match else "",
                    "task_path": task_path,
                },
            )
        )

        # The full task path is the source identity: two tasks that share a
        # leaf name in different folders must resolve to their own job.
        script_ref = task_path
        for candidate, hint in (
            (command, EntityType.SCRIPT),
            (_first_arg_path(args), EntityType.SCRIPT),
        ):
            if not candidate:
                continue
            name = candidate.replace("\\", "/").rstrip("/").split("/")[-1]
            result.entities.append(
                EntityCandidate(
                    entity_type=hint,
                    name=name,
                    qualified_name=candidate,
                    location=candidate,
                    technology="script",
                    confidence=Confidence.HIGH,
                    source_path=rel_path,
                    evidence_kind=EvidenceKind.SCHEDULER_ENTRY,
                    parser=self.name,
                )
            )
            result.relationships.append(
                RelationshipCandidate(
                    source_ref=script_ref,
                    source_type_hint=EntityType.SCHEDULED_JOB,
                    target_ref=candidate,
                    relationship_type=RelationshipType.RUNS,
                    target_type_hint=hint,
                    confidence=Confidence.CONFIRMED,
                    source_path=rel_path,
                    snippet=redact(f"{command} {args}").text,
                    evidence_kind=EvidenceKind.SCHEDULER_ENTRY,
                    parser=self.name,
                )
            )

    # -- cron ------------------------------------------------------------- #
    def _cron(
        self,
        result: ScanResult,
        rel_path: str,
        text: str,
        *,
        user_crontab: bool = False,
        user: str = "",
    ) -> None:
        for lineno, line in iter_lines(text):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            match = (
                _CRON_USER_LINE.match(stripped)
                if user_crontab
                else _CRON_LINE.match(stripped)
            )
            if not match:
                continue
            schedule = match.group("schedule").strip()
            command = match.group("command").strip()
            run_as = user if user_crontab else (match.group("user") or "")
            job_name = command.replace("\\", "/").split("/")[-1].split()[0] if command else f"cron-{lineno}"

            result.entities.append(
                EntityCandidate(
                    entity_type=EntityType.SCHEDULED_JOB,
                    name=job_name,
                    qualified_name=f"{schedule} {job_name}",
                    description=f"cron: {schedule}",
                    location=rel_path,
                    technology="cron",
                    confidence=Confidence.CONFIRMED,
                    source_path=rel_path,
                    line=lineno,
                    snippet=redact(stripped).text,
                    evidence_kind=EvidenceKind.CRON_EXPRESSION,
                    parser=self.name,
                    meta={
                        "schedule": schedule,
                        "command": command,
                        "run_as": run_as,
                        "crontab_kind": "user" if user_crontab else "system",
                        "crontab_user": user,
                    },
                )
            )
            result.relationships.append(
                RelationshipCandidate(
                    source_ref=f"{schedule} {job_name}",
                    source_type_hint=EntityType.SCHEDULED_JOB,
                    target_ref=command.split()[0] if command else "",
                    relationship_type=RelationshipType.RUNS,
                    target_type_hint=EntityType.SCRIPT,
                    confidence=Confidence.HIGH,
                    source_path=rel_path,
                    line=lineno,
                    snippet=redact(stripped).text,
                    evidence_kind=EvidenceKind.CRON_EXPRESSION,
                    parser=self.name,
                )
            )


def _crontab_context(path_lower: str, name: str) -> tuple[bool, str]:
    """Classify a cron artefact as a user or system crontab.

    Returns ``(is_user_crontab, user)``. A user crontab has no user column, so
    the exported owner (usually the filename) is captured explicitly.
    """
    parts = [p for p in path_lower.split("/") if p]
    if "cron.d" in parts:
        return False, ""
    if name == "crontab" or path_lower.endswith("/etc/crontab") or path_lower == "/etc/crontab":
        return False, ""
    if "crontabs" in parts or "var/spool/cron" in path_lower:
        return True, name
    # A file named `cron`/`cron.<user>` or living under a `cron` directory is
    # treated as the owning user's crontab when it is not an /etc artefact.
    if parts and parts[-2:-1] == ["cron"]:
        return True, name
    return False, ""


def _first_arg_path(args: str) -> str:
    for token in args.replace(",", " ").split():
        cleaned = token.strip("\"'")
        if cleaned.lower().endswith((".ps1", ".bat", ".cmd", ".py", ".sql", ".exe")):
            return cleaned
    return ""
