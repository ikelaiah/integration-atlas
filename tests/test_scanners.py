"""Scanner tests.

Fixtures are written as real artefacts — the kind of thing that actually turns
up in an enterprise integration folder — rather than synthetic strings chosen
to match the regexes. If a scanner stops recognising real code, these fail.
"""

from __future__ import annotations

from pathlib import Path

from atlas.domain import EntityType, RelationshipType
from atlas.scanners.base import read_text_safe
from atlas.scanners.config_scanner import ConfigScanner
from atlas.scanners.powershell_scanner import PowerShellScanner
from atlas.scanners.python_scanner import PythonScanner
from atlas.scanners.sql_scanner import SqlScanner

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "northstar"


def _read(rel: str) -> str:
    text = read_text_safe(EXAMPLES / rel)
    assert text is not None, f"fixture missing: {rel}"
    return text


def _find_rel(result, rel_type, *, contains: str | None = None):
    matches = [r for r in result.relationships if r.relationship_type is rel_type]
    if contains is not None:
        matches = [r for r in matches if contains.lower() in r.target_ref.lower()]
    return matches


# --------------------------------------------------------------------------- #
# Python
# --------------------------------------------------------------------------- #
def test_python_scanner_claims_python_files() -> None:
    scanner = PythonScanner()
    assert scanner.can_scan(EXAMPLES / "integrations/identity/identity_sync.py")
    assert not scanner.can_scan(EXAMPLES / "integrations/student/student_extract.sql")


def test_python_scanner_finds_http_calls() -> None:
    result = PythonScanner().scan(
        EXAMPLES / "integrations/identity/identity_sync.py",
        _read("integrations/identity/identity_sync.py"),
    )
    calls = _find_rel(result, RelationshipType.CALLS, contains="identity.northstar.edu")
    assert calls, "expected an SCIM call to IdentityHub"
    assert calls[0].confidence in {"high", "confirmed"}
    assert "identity_sync.py" in calls[0].source_path

    apis = [e for e in result.entities if e.entity_type is EntityType.API]
    assert any("identity.northstar.edu" in (a.qualified_name or "") for a in apis)


def test_python_scanner_finds_file_reads() -> None:
    result = PythonScanner().scan(
        EXAMPLES / "integrations/identity/identity_sync.py",
        _read("integrations/identity/identity_sync.py"),
    )
    consumes = _find_rel(result, RelationshipType.CONSUMES, contains="students.csv")
    assert consumes, "expected the student extract to be read"
    assert consumes[0].line is not None
    assert consumes[0].snippet


def test_python_scanner_finds_csv_write() -> None:
    source = (
        "import pandas as pd\n"
        "df.to_csv('/integrations/finance/fee_extract.csv', index=False)\n"
    )
    result = PythonScanner().scan(Path("finance_extract.py"), source)
    produces = _find_rel(result, RelationshipType.PRODUCES, contains="fee_extract.csv")
    assert produces


def test_python_scanner_finds_sql_tables_in_strings() -> None:
    source = (
        "query = '''\n"
        "SELECT s.StudentID, s.FirstName\n"
        "FROM Student.Person s\n"
        "JOIN Student.Enrolment e ON e.StudentID = s.StudentID\n"
        "'''\n"
    )
    result = PythonScanner().scan(Path("extract.py"), source)
    tables = {e.qualified_name for e in result.entities if e.entity_type is EntityType.TABLE}
    assert "Student.Person" in tables
    assert "Student.Enrolment" in tables
    reads = _find_rel(result, RelationshipType.READS_FROM, contains="Student.Person")
    assert reads


def test_python_scanner_finds_subprocess() -> None:
    source = "import subprocess\nsubprocess.run(['powershell.exe', '-File', 'export_students.ps1'], check=True)\n"
    result = PythonScanner().scan(Path("orchestrate.py"), source)
    assert _find_rel(result, RelationshipType.CALLS, contains="export_students.ps1")


def test_python_scanner_finds_database_connection() -> None:
    source = (
        "from sqlalchemy import create_engine\n"
        'engine = create_engine("mssql+pyodbc://SQL-PROD-01/FinancePro?driver=ODBC+Driver+17")\n'
    )
    result = PythonScanner().scan(Path("extract.py"), source)
    assert _find_rel(result, RelationshipType.CONNECTS_TO, contains="SQL-PROD-01")
    assert any(e.entity_type is EntityType.DATABASE for e in result.entities)


def test_python_scanner_records_the_script_itself() -> None:
    result = PythonScanner().scan(Path("identity_sync.py"), "print('hi')\n")
    scripts = [e for e in result.entities if e.entity_type is EntityType.SCRIPT]
    assert scripts and scripts[0].name == "identity_sync.py"


# --------------------------------------------------------------------------- #
# PowerShell
# --------------------------------------------------------------------------- #
def test_powershell_scanner_finds_sqlcmd() -> None:
    result = PowerShellScanner().scan(
        EXAMPLES / "integrations/student/export_students.ps1",
        _read("integrations/student/export_students.ps1"),
    )
    assert _find_rel(result, RelationshipType.CONNECTS_TO, contains="DB2-LEGACY-01")
    assert _find_rel(result, RelationshipType.CONNECTS_TO, contains="LegacySIS")
    assert _find_rel(result, RelationshipType.RUNS, contains="student_extract.sql")


def test_powershell_scanner_finds_file_operations() -> None:
    result = PowerShellScanner().scan(
        EXAMPLES / "integrations/student/export_students.ps1",
        _read("integrations/student/export_students.ps1"),
    )
    consumes = _find_rel(result, RelationshipType.CONSUMES)
    produces = _find_rel(result, RelationshipType.PRODUCES)
    transfers = _find_rel(result, RelationshipType.TRANSFERS_TO)
    assert consumes or produces or transfers, "expected at least one file operation"


def test_powershell_scanner_finds_unc_paths() -> None:
    result = PowerShellScanner().scan(
        EXAMPLES / "integrations/student/export_students.ps1",
        _read("integrations/student/export_students.ps1"),
    )
    uncs = [
        e
        for e in result.entities
        if e.technology == "UNC" or (e.location or "").startswith("\\\\")
    ]
    assert uncs, "expected the UNC share to be recorded"


def test_powershell_scanner_finds_rest_calls() -> None:
    source = (
        "Invoke-RestMethod -Uri https://api.payrollplus.example/v2/employees `\n"
        "  -Method Post -InFile .\\hr_positions.csv\n"
    )
    result = PowerShellScanner().scan(Path("hr_feed.ps1"), source)
    assert _find_rel(result, RelationshipType.CALLS, contains="api.payrollplus.example")


# --------------------------------------------------------------------------- #
# SQL
# --------------------------------------------------------------------------- #
def test_sql_scanner_extracts_tables_and_columns() -> None:
    result = SqlScanner().scan(
        EXAMPLES / "integrations/student/student_extract.sql",
        _read("integrations/student/student_extract.sql"),
    )
    tables = {e.qualified_name for e in result.entities if e.entity_type is EntityType.TABLE}
    assert "Student.Person" in tables
    assert "Student.Enrolment" in tables

    columns = {e.name for e in result.entities if e.entity_type is EntityType.COLUMN}
    assert {"StudentID", "FirstName", "LastName", "YearLevel"} <= columns

    reads = _find_rel(result, RelationshipType.READS_FROM, contains="Student.Person")
    assert reads and reads[0].confidence in {"high", "confirmed"}


def test_sql_scanner_distinguishes_reads_from_writes() -> None:
    result = SqlScanner().scan(
        EXAMPLES / "integrations/reports/reporting_extract.sql",
        _read("integrations/reports/reporting_extract.sql"),
    )
    writes = _find_rel(result, RelationshipType.WRITES_TO, contains="dim_student")
    reads = _find_rel(result, RelationshipType.READS_FROM, contains="Student.Person")
    assert writes, "INSERT INTO mart.dim_student should be a write"
    assert reads, "SELECT FROM Student.Person should be a read"


def test_sql_scanner_records_schema_parents() -> None:
    result = SqlScanner().scan(
        EXAMPLES / "integrations/reports/reporting_extract.sql",
        _read("integrations/reports/reporting_extract.sql"),
    )
    schemas = {e.name for e in result.entities if e.entity_type is EntityType.SCHEMA}
    assert {"mart", "Student"} <= schemas


def test_sql_scanner_handles_quoted_identifiers() -> None:
    source = 'SELECT "StudentID" FROM "Student"."Person";\n'
    result = SqlScanner().scan(Path("q.sql"), source)
    tables = {e.qualified_name for e in result.entities if e.entity_type is EntityType.TABLE}
    assert any("Person" in t for t in tables)


def test_sql_scanner_tolerates_comments_and_strings() -> None:
    source = (
        "-- SELECT * FROM ShouldNotAppear; /* block */\n"
        "SELECT 'literal; with semicolon' AS note, StudentID FROM Student.Person;\n"
    )
    result = SqlScanner().scan(Path("c.sql"), source)
    tables = {e.qualified_name for e in result.entities if e.entity_type is EntityType.TABLE}
    assert "Student.Person" in tables
    assert "ShouldNotAppear" not in tables


# --------------------------------------------------------------------------- #
# Config / scheduler
# --------------------------------------------------------------------------- #
def test_config_scanner_reads_ini_keys() -> None:
    result = ConfigScanner().scan(
        EXAMPLES / "integrations/enrolment/settings.ini",
        _read("integrations/enrolment/settings.ini"),
    )
    servers = [e for e in result.entities if e.entity_type is EntityType.SERVER]
    assert any(e.name == "SQL-PROD-01" for e in servers)
    databases = [e for e in result.entities if e.entity_type is EntityType.DATABASE]
    assert any(e.name == "PortalDB" for e in databases)


def test_config_scanner_finds_urls_in_json() -> None:
    result = ConfigScanner().scan(
        EXAMPLES / "integrations/enrolment/config.json",
        _read("integrations/enrolment/config.json"),
    )
    apis = [e for e in result.entities if e.entity_type is EntityType.API]
    assert any("enrol.northstar.edu" in (a.qualified_name or "") for a in apis)


def test_config_scanner_finds_urls_in_yaml() -> None:
    result = ConfigScanner().scan(
        EXAMPLES / "integrations/identity/config.yaml",
        _read("integrations/identity/config.yaml"),
    )
    apis = [e for e in result.entities if e.entity_type is EntityType.API]
    assert any("identity.northstar.edu" in (a.qualified_name or "") for a in apis)


def test_config_scanner_reads_env_example() -> None:
    result = ConfigScanner().scan(
        EXAMPLES / "integrations/enrolment/.env.example",
        _read("integrations/enrolment/.env.example"),
    )
    names = {e.name for e in result.entities}
    assert "ENROLMENT_DB_HOST" in names or "SQL-PROD-01" in names


def test_task_scheduler_xml_extracts_command_and_schedule() -> None:
    result = ConfigScanner().scan(
        EXAMPLES / "windows/tasks/nightly-student-export.xml",
        _read("windows/tasks/nightly-student-export.xml"),
    )
    jobs = [e for e in result.entities if e.entity_type is EntityType.SCHEDULED_JOB]
    assert jobs, "expected a scheduled job"
    job = jobs[0]
    assert "nightly-student-export" in job.name
    assert job.meta.get("command"), "the task must record its command"
    assert "export_students.ps1" in (job.meta.get("arguments") or ""), (
        "the scheduled arguments should name the script"
    )
    assert job.meta.get("schedule"), "the schedule must be extracted"

    runs = _find_rel(result, RelationshipType.RUNS, contains="export_students.ps1")
    assert runs, "the task must be linked to the script it runs"


def test_cron_entry_extracts_schedule_and_command() -> None:
    result = ConfigScanner().scan(
        EXAMPLES / "linux/cron.d/integrations",
        _read("linux/cron.d/integrations"),
    )
    jobs = [e for e in result.entities if e.entity_type is EntityType.SCHEDULED_JOB]
    assert len(jobs) >= 3, "expected several cron jobs"
    schedules = {j.meta.get("schedule") for j in jobs}
    assert "*/15 * * * *" in schedules

    runs = _find_rel(result, RelationshipType.RUNS, contains="identity_sync.py")
    assert runs


def test_config_scanner_warns_on_malformed_json() -> None:
    result = ConfigScanner().scan(Path("broken.json"), "{ not json ")
    assert result.warnings, "malformed JSON should produce a warning, not a crash"


# --------------------------------------------------------------------------- #
# Secret redaction across the pipeline
# --------------------------------------------------------------------------- #
def test_config_password_is_redacted_at_scan_time() -> None:
    text = _read("integrations/enrolment/settings.ini")
    assert "ChangeMeOnNextDeploy!" in text, "fixture must contain a fake secret"
    result = ConfigScanner().scan(
        EXAMPLES / "integrations/enrolment/settings.ini", text
    )
    for entity in result.entities:
        blob = f"{entity.description} {entity.location} {entity.snippet} {entity.meta}"
        assert "ChangeMeOnNextDeploy!" not in blob
    for rel in result.relationships:
        assert "ChangeMeOnNextDeploy!" not in (rel.snippet or "")


def test_never_stores_api_keys_from_config() -> None:
    text = (
        "[api]\n"
        "api_key = api-test-key-do-not-use\n"
        "endpoint = https://api.example.com/v1\n"
    )
    result = ConfigScanner().scan(Path("app.ini"), text)
    blob = repr(
        [(e.description, e.location, e.snippet, e.meta) for e in result.entities]
        + [(r.snippet,) for r in result.relationships]
    )
    assert "api-test-key-do-not-use" not in blob


def test_python_scanner_never_stores_bearer_tokens() -> None:
    source = (
        "import requests\n"
        'token = "abcdef1234567890abcd"\n'
        'requests.get("https://api.example.com/v1", headers={"Authorization": f"Bearer {token}"})\n'
    )
    result = PythonScanner().scan(Path("x.py"), source)
    blob = repr([e.snippet for e in result.entities] + [r.snippet for r in result.relationships])
    assert "abcdef1234567890abcd" not in blob


def test_powershell_scanner_never_stores_connection_passwords() -> None:
    source = (
        "$conn = 'Server=SQL-PROD-01;Database=FinancePro;Password=ProdFinance!2024x'\n"
        "Invoke-Sqlcmd -ConnectionString $conn -Query 'SELECT 1'\n"
    )
    result = PowerShellScanner().scan(Path("f.ps1"), source)
    blob = repr([e.snippet for e in result.entities] + [r.snippet for r in result.relationships])
    assert "ProdFinance!2024x" not in blob


# --------------------------------------------------------------------------- #
# Robustness
# --------------------------------------------------------------------------- #
def test_read_text_safe_handles_encodings() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "latin.txt"
        path.write_bytes("caf\xe9 = value\n".encode("cp1252"))
        text = read_text_safe(path)
        assert text is not None and "café" in text


def test_scanners_do_not_crash_on_binary_looking_text() -> None:
    weird = "\x00\x01\x02 SELECT * FROM T; \x03"
    for scanner in (PythonScanner(), PowerShellScanner(), SqlScanner(), ConfigScanner()):
        result = scanner.scan(Path("weird.sql"), weird)
        assert result is not None


def test_empty_file_produces_empty_result() -> None:
    result = SqlScanner().scan(Path("empty.sql"), "")
    assert result.is_empty or all(e.entity_type is EntityType.SCRIPT for e in result.entities)
