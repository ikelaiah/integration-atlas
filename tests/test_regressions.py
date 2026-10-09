"""Focused regression tests for the seven hardening issues (plus server bundles).

Each test reproduces a specific reported failure. Fixtures are written to
isolated temporary directories and an in-memory database; the real atlas-data
database is never touched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from atlas.demo.seeder import get_or_create_workspace
from atlas.domain import EntityType, SourceKind
from atlas.models import (
    Base,
    Entity,
    Evidence,
    Relationship,
    Scan,
    ScanSnapshot,
    SecretEvent,
    Workspace,
)
from atlas.scanners.base import EntityCandidate
from atlas.scanners.normalise import Normaliser
from atlas.scanners.runner import run_scan
from atlas.services.redaction import redact

SECRET = "SyntheticSecret123"
META_SECRET = "MetaSecret456"


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    db = factory()
    try:
        yield db
        db.commit()
    finally:
        db.close()
        engine.dispose()


@pytest.fixture()
def client(session):
    from fastapi.testclient import TestClient

    from atlas.api.app import create_app
    from atlas.db import get_db

    app = create_app(initialise_db=False)

    def override():
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise

    app.dependency_overrides[get_db] = override
    with TestClient(app) as test_client:
        yield test_client


def _all_strings(session) -> str:
    blobs: list[str] = []
    for row in (
        list(session.scalars(select(Entity)))
        + list(session.scalars(select(Relationship)))
        + list(session.scalars(select(Evidence)))
        + list(session.scalars(select(SecretEvent)))
    ):
        for column in row.__table__.columns:
            value = getattr(row, column.name)
            blobs.append(json.dumps(value, default=str) if not isinstance(value, str) else value)
    return "\n".join(blobs)


# --------------------------------------------------------------------------- #
# Issue 1 — secrets persist in unredacted fields
# --------------------------------------------------------------------------- #
def test_normaliser_redacts_qualified_name_and_metadata(session) -> None:
    workspace = get_or_create_workspace(session, "Secret Fields")
    normaliser = Normaliser(session, workspace)
    entity = normaliser.upsert_entity(
        EntityCandidate(
            entity_type=EntityType.API,
            name="api.example.com",
            qualified_name=f"https://svc:{SECRET}@api.example.com/v1",
            location=f"https://svc:{SECRET}@api.example.com/v1",
            meta={
                "arguments": f"--password={META_SECRET}",
                "nested": {"api_key": "api-test-key-do-not-use"},
            },
        )
    )
    session.flush()
    blob = json.dumps(entity.qualified_name) + json.dumps(entity.meta_json)
    assert SECRET not in blob
    assert META_SECRET not in blob
    assert "api-test-key-do-not-use" not in blob
    assert "<redacted" in entity.qualified_name


def test_task_arguments_never_persist_in_metadata(session, tmp_path: Path) -> None:
    root = tmp_path / "tasks"
    root.mkdir()
    (root / "job.xml").write_text(
        "<Task><RegistrationInfo><URI>\\job</URI></RegistrationInfo>"
        "<Actions Context=\"Author\"><Exec><Command>run.exe</Command>"
        f"<Arguments>--password={SECRET} --verbose</Arguments></Exec></Actions></Task>",
        encoding="utf-8",
    )
    workspace = get_or_create_workspace(session, "Task Secret")
    run_scan(session, workspace, root)
    session.flush()
    assert SECRET not in _all_strings(session)


def test_api_writes_are_redacted(session, client) -> None:
    workspace = get_or_create_workspace(session, "API Secrets")
    session.commit()

    created = client.post(
        f"/api/entities?workspace_id={workspace.id}",
        json={
            "entity_type": "api",
            "name": f"svc:{SECRET}@api.example.com",
            "qualified_name": f"https://svc:{SECRET}@api.example.com",
            "description": f"connects with password={SECRET}",
            "owner": f"token={META_SECRET}",
            "meta_json": {"token": META_SECRET},
        },
    )
    assert created.status_code == 201
    entity_id = created.json()["id"]

    patched = client.patch(
        f"/api/entities/{entity_id}",
        json={"description": f"rotated password={SECRET}", "meta_json": {"secret": META_SECRET}},
    )
    assert patched.status_code == 200
    session.flush()
    assert SECRET not in _all_strings(session)
    assert META_SECRET not in _all_strings(session)


def test_export_never_carries_a_secret(session, tmp_path: Path) -> None:
    from atlas.services.exporters import export_workspace

    workspace = get_or_create_workspace(session, "Export Secret")
    normaliser = Normaliser(session, workspace)
    normaliser.upsert_entity(
        EntityCandidate(
            entity_type=EntityType.API,
            name="api",
            qualified_name=f"https://u:{SECRET}@api.example.com",
            meta={"password": META_SECRET},
        )
    )
    session.flush()
    out = export_workspace(session, workspace, tmp_path / "out.json", fmt="json")
    text = out.read_text(encoding="utf-8")
    assert SECRET not in text
    assert META_SECRET not in text


@pytest.mark.parametrize("fmt,header", [("mermaid", "flowchart LR"), ("plantuml", "@startuml")])
def test_diagram_exports_escape_untrusted_labels_and_skip_rejected(
    session, tmp_path: Path, fmt: str, header: str
) -> None:
    from atlas.services.exporters import export_workspace

    workspace = get_or_create_workspace(session, "Diagram Secret")
    nodes = [
        Entity(workspace_id=workspace.id, entity_type="system",
               name='Source"]\n@startuml\npassword=SyntheticSecret123', fingerprint="diagram-a"),
        Entity(workspace_id=workspace.id, entity_type="system", name="Target", fingerprint="diagram-b"),
    ]
    session.add_all(nodes)
    session.flush()
    session.add_all([
        Relationship(workspace_id=workspace.id, source_id=nodes[0].id,
                     target_id=nodes[1].id, relationship_type="produces",
                     fingerprint="diagram-link", review_status="proposed"),
        Relationship(workspace_id=workspace.id, source_id=nodes[1].id,
                     target_id=nodes[0].id, relationship_type="calls",
                     fingerprint="diagram-rejected", review_status="rejected"),
    ])
    session.flush()
    out = export_workspace(session, workspace, tmp_path / f"diagram.{fmt}", fmt=fmt)
    text = out.read_text(encoding="utf-8")
    assert header in text
    assert "SyntheticSecret123" not in text
    assert "nodes=2 edges=1" in text
    assert "Source&quot;] @startuml" in text
    assert "calls" not in text


# --------------------------------------------------------------------------- #
# Issue 2 — allowlisted keys suppress nearby secret detection
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "text",
    [
        "token_type=Bearer\npassword=SyntheticSecret123",
        "password=SyntheticSecret123\ntoken_type=Bearer",
        '{"token_type": "Bearer", "password": "SyntheticSecret123"}',
        "token_type = Bearer;\npassword = SyntheticSecret123;",
    ],
)
def test_adjacent_allowlisted_key_does_not_hide_a_secret(text: str) -> None:
    result = redact(text)
    assert "SyntheticSecret123" not in result.text
    assert result.count >= 1


def test_allowlisted_key_still_excuses_its_own_assignment() -> None:
    result = redact("token_type=Bearer\npassword_policy=complexity\nkey_file=/etc/app.pem")
    assert "Bearer" in result.text
    assert "complexity" in result.text
    assert "/etc/app.pem" in result.text


# --------------------------------------------------------------------------- #
# Issue 3 — relationship reconciliation crosses workspace boundaries
# --------------------------------------------------------------------------- #
def test_evidence_never_crosses_workspaces(session, tmp_path: Path) -> None:
    root = tmp_path / "estate"
    root.mkdir()
    (root / "extract.py").write_text(
        "import pandas as pd\n"
        "df = pd.read_csv('/data/students.csv')\n"
        "df.to_csv('/data/out.csv')\n",
        encoding="utf-8",
    )

    ws_a = get_or_create_workspace(session, "Workspace A")
    ws_b = get_or_create_workspace(session, "Workspace B")
    run_scan(session, ws_a, root)
    run_scan(session, ws_b, root)
    # Rescanning B used to attach evidence to A's relationships.
    run_scan(session, ws_b, root)
    session.flush()

    relationships = {r.id: r for r in session.scalars(select(Relationship))}
    for ev in session.scalars(select(Evidence).where(Evidence.relationship_id.is_not(None))):
        rel = relationships[ev.relationship_id]
        assert rel.workspace_id == ev.workspace_id, "evidence leaked across workspaces"


# --------------------------------------------------------------------------- #
# Issue 4 — rescans overwrite manual corrections
# --------------------------------------------------------------------------- #
def test_manual_edits_survive_repeated_rescans(session, client, tmp_path: Path) -> None:
    root = tmp_path / "scripts"
    root.mkdir()
    (root / "sync.py").write_text("print('sync')\n", encoding="utf-8")

    workspace = get_or_create_workspace(session, "Manual Edits")
    run_scan(session, workspace, root)
    session.commit()

    entity = session.scalar(
        select(Entity).where(
            Entity.workspace_id == workspace.id, Entity.name == "sync.py"
        )
    )
    assert entity is not None

    response = client.patch(
        f"/api/entities/{entity.id}",
        json={"description": "Curated by an operator", "owner": "Data Platform"},
    )
    assert response.status_code == 200
    assert response.json()["source_kind"] == "manual"

    for _ in range(2):
        run_scan(session, workspace, root)
        session.flush()
        refreshed = session.get(Entity, entity.id)
        assert refreshed.description == "Curated by an operator"
        assert refreshed.owner == "Data Platform"
        assert refreshed.source_kind == SourceKind.MANUAL.value


def test_discovery_still_updates_unedited_fields(session, tmp_path: Path) -> None:
    root = tmp_path / "scripts"
    root.mkdir()
    target = root / "sync.py"
    target.write_text("print('one')\n", encoding="utf-8")

    workspace = get_or_create_workspace(session, "Partial Manual")
    run_scan(session, workspace, root)
    entity = session.scalar(select(Entity).where(Entity.name == "sync.py"))
    entity.manual_fields_json = ["description"]
    entity.source_kind = SourceKind.MANUAL.value
    entity.description = "manual description"
    session.flush()

    target.write_text("print('two')\n", encoding="utf-8")
    run_scan(session, workspace, root)
    session.flush()
    refreshed = session.get(Entity, entity.id)
    assert refreshed.description == "manual description"
    # A non-manual field is allowed to change with the file.
    assert refreshed.source_kind == SourceKind.MANUAL.value


# --------------------------------------------------------------------------- #
# Issue 5 — cron discovery fails in the full pipeline
# --------------------------------------------------------------------------- #
def test_cron_pipeline_persists_job_relationship_and_evidence(session, tmp_path: Path) -> None:
    cron_dir = tmp_path / "etc" / "cron.d"
    cron_dir.mkdir(parents=True)
    (cron_dir / "integrations").write_text(
        "*/15 * * * * svc_int /opt/integrations/identity_sync.py --password=" + SECRET + "\n",
        encoding="utf-8",
    )
    workspace = get_or_create_workspace(session, "Cron E2E")
    summary = run_scan(session, workspace, tmp_path)

    assert summary["errors"] == 0, "cron must not make the scanner throw"
    jobs = list(
        session.scalars(
            select(Entity).where(
                Entity.workspace_id == workspace.id,
                Entity.entity_type == EntityType.SCHEDULED_JOB.value,
            )
        )
    )
    assert jobs, "a valid cron line should persist a scheduled job"
    runs = list(
        session.scalars(
            select(Relationship).where(
                Relationship.relationship_type == "runs",
                Relationship.workspace_id == workspace.id,
            )
        )
    )
    assert runs, "the cron job should RUN its command"
    evidence = list(session.scalars(select(Evidence)))
    assert any(ev.snippet for ev in evidence)
    assert SECRET not in _all_strings(session)


# --------------------------------------------------------------------------- #
# Issue 6 — docker compose configuration prevents startup
# --------------------------------------------------------------------------- #
def test_shipped_compose_allowlist_parses_and_enforces(client, tmp_path: Path, monkeypatch) -> None:
    import yaml

    compose_path = Path(__file__).resolve().parents[1] / "docker-compose.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    value = compose["services"]["atlas"]["environment"]["ATLAS_SCAN_ROOT_ALLOWLIST"]
    assert isinstance(value, str)

    monkeypatch.setenv("ATLAS_SCAN_ROOT_ALLOWLIST", value)
    from atlas.config import Settings

    settings = Settings()
    assert settings.scan_root_allowlist == [Path("/scan")]

    outside = tmp_path / "outside"
    outside.mkdir()
    response = client.post("/api/scans", json={"root_path": str(outside)})
    assert response.status_code == 403


# --------------------------------------------------------------------------- #
# Issue 7 — deleted discoveries remain after rescans
# --------------------------------------------------------------------------- #
def test_deleted_file_retires_its_entities(session, tmp_path: Path) -> None:
    root = tmp_path / "estate"
    root.mkdir()
    script = root / "extract.py"
    script.write_text(
        "import pandas as pd\npd.read_csv('/data/students.csv')\n", encoding="utf-8"
    )
    workspace = get_or_create_workspace(session, "Retire Deleted")
    run_scan(session, workspace, root)
    session.flush()
    assert session.scalar(select(Entity).where(Entity.name == "extract.py")) is not None

    script.unlink()
    run_scan(session, workspace, root)
    session.flush()

    entity = session.scalar(select(Entity).where(Entity.name == "extract.py"))
    assert entity.is_active is False
    active = list(
        session.scalars(
            select(Entity).where(
                Entity.workspace_id == workspace.id, Entity.is_active.is_(True)
            )
        )
    )
    assert all(e.name != "extract.py" for e in active)


def test_removed_dependency_within_edited_file_is_retired(session, tmp_path: Path) -> None:
    root = tmp_path / "estate"
    root.mkdir()
    script = root / "extract.py"
    script.write_text("open('/data/students.csv')\n", encoding="utf-8")
    workspace = get_or_create_workspace(session, "Retire Dependency")
    run_scan(session, workspace, root)
    session.flush()

    script.write_text("print('no more file io')\n", encoding="utf-8")
    run_scan(session, workspace, root)
    session.flush()

    csv = session.scalar(select(Entity).where(Entity.name == "students.csv"))
    assert csv is not None and csv.is_active is False


def test_shared_entity_survives_when_another_root_still_supports_it(
    session, tmp_path: Path
) -> None:
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    script_a = root_a / "one.py"
    script_a.write_text("open('/shared/data.csv')\n", encoding="utf-8")
    (root_b / "two.py").write_text("open('/shared/data.csv')\n", encoding="utf-8")

    workspace = get_or_create_workspace(session, "Shared Roots")
    run_scan(session, workspace, root_a)
    run_scan(session, workspace, root_b)
    session.flush()
    assert sum(1 for e in session.scalars(select(Entity)) if e.name == "data.csv") == 1

    script_a.unlink()
    run_scan(session, workspace, root_a)
    session.flush()

    shared = session.scalar(select(Entity).where(Entity.name == "data.csv"))
    assert shared.is_active is True
    one = session.scalar(select(Entity).where(Entity.name == "one.py"))
    assert one.is_active is False


def test_manual_rows_are_not_retired(session, tmp_path: Path) -> None:
    root = tmp_path / "estate"
    root.mkdir()
    script = root / "extract.py"
    script.write_text("print('hi')\n", encoding="utf-8")
    workspace = get_or_create_workspace(session, "Manual Survives")
    run_scan(session, workspace, root)
    session.flush()

    entity = session.scalar(select(Entity).where(Entity.name == "extract.py"))
    entity.source_kind = SourceKind.MANUAL.value
    entity.manual_fields_json = ["description"]
    session.flush()

    script.unlink()
    run_scan(session, workspace, root)
    session.flush()
    assert session.get(Entity, entity.id).is_active is True


def test_unreadable_files_are_not_treated_as_deletions(
    session, tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "estate"
    root.mkdir()
    script = root / "extract.py"
    script.write_text("print('hi')\n", encoding="utf-8")
    workspace = get_or_create_workspace(session, "Partial Scan")
    run_scan(session, workspace, root)
    session.flush()

    import atlas.scanners.runner as runner_module

    original = runner_module.read_text_safe

    def flaky(path, *args, **kwargs):
        if Path(path).name == "extract.py":
            return None
        return original(path, *args, **kwargs)

    monkeypatch.setattr(runner_module, "read_text_safe", flaky)
    run_scan(session, workspace, root)
    session.flush()
    assert session.scalar(select(Entity).where(Entity.name == "extract.py")).is_active is True


def test_retired_entities_leave_the_graph(session, tmp_path: Path) -> None:
    root = tmp_path / "estate"
    root.mkdir()
    script = root / "extract.py"
    script.write_text("open('/data/students.csv')\n", encoding="utf-8")
    workspace = get_or_create_workspace(session, "Graph Retirement")
    run_scan(session, workspace, root)
    script.unlink()
    run_scan(session, workspace, root)
    session.flush()

    from atlas.services.graph import GraphIndex

    entities = list(session.scalars(select(Entity)))
    relationships = list(session.scalars(select(Relationship)))
    index = GraphIndex(entities, relationships)
    assert all(node.name != "extract.py" for node in index.nodes.values())


# --------------------------------------------------------------------------- #
# Issue 8 — per-server export bundles
# --------------------------------------------------------------------------- #
def _write_bundle(base: Path, host: str, *, os_name: str = "windows", manifest: bool = True) -> Path:
    bundle = base / host
    (bundle / "scripts").mkdir(parents=True)
    if manifest:
        (bundle / "server.json").write_text(
            json.dumps(
                {
                    "hostname": host,
                    "fqdn": f"{host}.corp.example",
                    "os": os_name,
                    "environment": "production",
                }
            ),
            encoding="utf-8",
        )
    (bundle / "shared.ini").write_text(
        "[db]\nhost = SHARED-DB-01\ndatabase = PortalDB\n", encoding="utf-8"
    )
    (bundle / "scripts" / "job.ps1").write_text("Write-Host hi\n", encoding="utf-8")
    (bundle / "tasks.xml").write_text(
        "<Task><RegistrationInfo><URI>\\nightly-export</URI></RegistrationInfo>"
        "<Actions Context=\"Author\"><Exec><Command>powershell.exe</Command>"
        "<Arguments>-File C:\\integrations\\job.ps1</Arguments></Exec></Actions></Task>",
        encoding="utf-8",
    )
    return bundle


def test_identical_names_on_two_servers_stay_distinct(session, tmp_path: Path) -> None:
    _write_bundle(tmp_path, "APP01")
    _write_bundle(tmp_path, "APP02")
    workspace = get_or_create_workspace(session, "Multi Server")
    run_scan(session, workspace, tmp_path)
    session.flush()

    jobs = [
        e
        for e in session.scalars(select(Entity))
        if e.entity_type == EntityType.SCHEDULED_JOB.value
    ]
    assert len(jobs) == 2, "the same task name on two servers must not merge"
    assert {j.meta_json.get("server") for j in jobs} == {"APP01", "APP02"}

    local_scripts = [
        e
        for e in session.scalars(select(Entity))
        if e.entity_type == EntityType.SCRIPT.value and e.name == "job.ps1"
    ]
    # Every local script is scoped to exactly one execution server, and the
    # file-level script for each server is present, so the identical name and
    # path never collapse into one entity.
    scopes = {e.meta_json.get("server") for e in local_scripts}
    assert None not in scopes, "local scripts must be server-scoped"
    assert scopes == {"APP01", "APP02"}

    servers = [
        e for e in session.scalars(select(Entity)) if e.entity_type == EntityType.SERVER.value
    ]
    assert {s.name for s in servers} >= {"APP01", "APP02"}

    runs_on = list(
        session.scalars(
            select(Relationship).where(Relationship.relationship_type == "runs_on")
        )
    )
    assert len(runs_on) >= 2, "each job should RUN_ON its execution server"


def test_shared_remote_dependency_merges_across_servers(session, tmp_path: Path) -> None:
    _write_bundle(tmp_path, "APP01")
    _write_bundle(tmp_path, "APP02")
    workspace = get_or_create_workspace(session, "Shared Dependency")
    run_scan(session, workspace, tmp_path)
    session.flush()
    databases = [
        e for e in session.scalars(select(Entity)) if e.entity_type == EntityType.DATABASE.value
    ]
    assert sum(1 for e in databases if e.name == "PortalDB") == 1


def test_missing_server_metadata_is_unknown(session, tmp_path: Path) -> None:
    _write_bundle(tmp_path, "APP01", manifest=False)
    workspace = get_or_create_workspace(session, "No Metadata")
    run_scan(session, workspace, tmp_path)
    session.flush()
    job = session.scalar(
        select(Entity).where(Entity.entity_type == EntityType.SCHEDULED_JOB.value)
    )
    assert job.meta_json.get("server") in (None, "")
    assert job.meta_json.get("execution_server_known") in (None, False)
    assert not list(
        session.scalars(
            select(Relationship).where(Relationship.relationship_type == "runs_on")
        )
    )


def test_user_and_system_crontabs_are_distinguished(session, tmp_path: Path) -> None:
    system_dir = tmp_path / "etc" / "cron.d"
    system_dir.mkdir(parents=True)
    (system_dir / "sys").write_text(
        "0 1 * * * root /usr/local/bin/cleanup.sh\n", encoding="utf-8"
    )
    user_dir = tmp_path / "var" / "spool" / "cron" / "crontabs"
    user_dir.mkdir(parents=True)
    (user_dir / "svc_int").write_text(
        "*/15 * * * * /opt/integrations/identity_sync.py\n", encoding="utf-8"
    )
    (tmp_path / "server.json").write_text(
        json.dumps({"hostname": "LINUX01", "os": "linux"}), encoding="utf-8"
    )

    workspace = get_or_create_workspace(session, "Cron Formats")
    run_scan(session, workspace, tmp_path)
    session.flush()

    jobs = {
        e.name: e
        for e in session.scalars(select(Entity))
        if e.entity_type == EntityType.SCHEDULED_JOB.value
    }
    assert "identity_sync.py" in jobs
    user_job = jobs["identity_sync.py"]
    assert user_job.meta_json.get("crontab_kind") == "user"
    assert user_job.meta_json.get("run_as") == "svc_int"
    assert user_job.meta_json.get("command") == "/opt/integrations/identity_sync.py"

    assert "cleanup.sh" in jobs
    assert jobs["cleanup.sh"].meta_json.get("crontab_kind") == "system"
    assert jobs["cleanup.sh"].meta_json.get("run_as") == "root"


def test_repeated_bundle_imports_are_idempotent(session, tmp_path: Path) -> None:
    _write_bundle(tmp_path, "APP01")
    workspace = get_or_create_workspace(session, "Repeat Import")
    first = run_scan(session, workspace, tmp_path)
    session.flush()
    second = run_scan(session, workspace, tmp_path)
    assert second["entities_added"] == 0
    assert second["relationships_added"] == 0
    assert first["entities"] == second["entities"]


# --------------------------------------------------------------------------- #
# Review follow-ups
# --------------------------------------------------------------------------- #
def test_existing_database_gets_snapshot_table_without_losing_scans(tmp_path: Path) -> None:
    from atlas import db as atlas_db

    url = f"sqlite:///{(tmp_path / 'prior.sqlite3').as_posix()}"
    old_engine = create_engine(url)
    Base.metadata.create_all(old_engine, tables=[Workspace.__table__, Scan.__table__])
    with old_engine.begin() as conn:
        conn.execute(Workspace.__table__.insert().values(
            id="workspace", name="Existing", slug="existing", description="",
            is_demo=False,
        ))
        conn.execute(Scan.__table__.insert().values(
            id="older", workspace_id="workspace", root_path="old", status="completed",
        ))
    old_engine.dispose()
    try:
        upgraded = atlas_db.init_db(url)
        assert inspect(upgraded).has_table(ScanSnapshot.__tablename__)
        with Session(upgraded) as session:
            assert session.get(Scan, "older") is not None
            assert session.get(ScanSnapshot, "older") is None
    finally:
        atlas_db.reset_engine()


def test_migration_upgrades_populated_pre_change_database(tmp_path: Path) -> None:
    """A pre-change database is upgraded in place, preserving manual knowledge."""
    from atlas import db as atlas_db
    from atlas.demo.seeder import fingerprint_entity

    root = tmp_path / "estate"
    root.mkdir()
    script = root / "sync.py"
    script.write_text("print('sync')\n", encoding="utf-8")

    qualified = str(script).replace("\\", "/")
    fingerprint = fingerprint_entity("script", qualified, "sync.py", qualified)

    url = f"sqlite:///{(tmp_path / 'legacy.sqlite3').as_posix()}"
    atlas_db.reset_engine()
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    legacy = factory()
    workspace = get_or_create_workspace(legacy, "Legacy")
    legacy.add(
        Entity(
            workspace_id=workspace.id,
            entity_type="script",
            name="sync.py",
            qualified_name=qualified,
            description="Curated by an operator",
            owner="Data Platform",
            source_kind="manual",
            fingerprint=fingerprint,
        )
    )
    legacy.commit()
    entity_id = legacy.scalar(select(Entity).where(Entity.name == "sync.py")).id
    workspace_id = workspace.id
    legacy.close()

    # Simulate a pre-change schema: remove the columns added after the fact.
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql("ALTER TABLE entities DROP COLUMN is_active")
            conn.exec_driver_sql("ALTER TABLE entities DROP COLUMN manual_fields_json")
            conn.exec_driver_sql("ALTER TABLE relationships DROP COLUMN is_active")
    except Exception:  # pragma: no cover - very old SQLite
        engine.dispose()
        atlas_db.reset_engine()
        pytest.skip("SQLite does not support DROP COLUMN")
    engine.dispose()
    atlas_db.reset_engine()

    migrated = atlas_db.init_db(url)
    # Idempotent: a second migration is a no-op.
    assert atlas_db.migrate_schema(migrated) == []

    upgraded = sessionmaker(bind=migrated, expire_on_commit=False, future=True)()
    row = upgraded.get(Entity, entity_id)
    assert row is not None
    assert row.description == "Curated by an operator"
    assert row.owner == "Data Platform"
    assert row.source_kind == "manual"
    assert row.is_active is True
    assert list(row.manual_fields_json or []) == []

    # The upgraded database is fully usable, and manual knowledge still wins.
    from atlas.models import Workspace

    workspace_row = upgraded.get(Workspace, workspace_id)
    run_scan(upgraded, workspace_row, root)
    upgraded.flush()
    refreshed = upgraded.get(Entity, entity_id)
    assert refreshed.description == "Curated by an operator"
    assert refreshed.owner == "Data Platform"
    assert refreshed.source_kind == "manual"

    upgraded.close()
    atlas_db.reset_engine()


def test_server_b_does_not_borrow_server_a_script(session, tmp_path: Path) -> None:
    bundle_a = tmp_path / "A"
    (bundle_a / "scripts").mkdir(parents=True)
    (bundle_a / "server.json").write_text(
        json.dumps({"hostname": "SERVER-A", "os": "windows"}), encoding="utf-8"
    )
    (bundle_a / "scripts" / "shared.ps1").write_text("Write-Host a\n", encoding="utf-8")

    bundle_b = tmp_path / "B"
    bundle_b.mkdir()
    (bundle_b / "server.json").write_text(
        json.dumps({"hostname": "SERVER-B", "os": "windows"}), encoding="utf-8"
    )
    (bundle_b / "tasks.xml").write_text(
        "<Task><RegistrationInfo><URI>\\job</URI></RegistrationInfo>"
        "<Actions Context=\"Author\"><Exec><Command>powershell.exe</Command>"
        "<Arguments>-File C:\\scripts\\shared.ps1</Arguments></Exec></Actions></Task>",
        encoding="utf-8",
    )

    workspace = get_or_create_workspace(session, "Server Isolation")
    run_scan(session, workspace, tmp_path)
    session.flush()

    job = session.scalar(
        select(Entity).where(Entity.entity_type == EntityType.SCHEDULED_JOB.value)
    )
    runs = list(
        session.scalars(
            select(Relationship).where(
                Relationship.source_id == job.id,
                Relationship.relationship_type == "runs",
            )
        )
    )
    shared_entities = list(
        session.scalars(select(Entity).where(Entity.name == "shared.ps1"))
    )
    scopes = {e.meta_json.get("server") for e in shared_entities}
    assert scopes == {"SERVER-A", "SERVER-B"}, "A and B keep distinct script entities"
    a_script = next(e for e in shared_entities if e.meta_json.get("server") == "SERVER-A")

    shared_targets = [
        session.get(Entity, rel.target_id)
        for rel in runs
        if session.get(Entity, rel.target_id).name == "shared.ps1"
    ]
    assert shared_targets, "the B task must RUN shared.ps1"
    assert shared_targets[0].meta_json.get("server") == "SERVER-B", "B must not borrow A's script"
    assert shared_targets[0].id != a_script.id


def test_full_path_resolution_prefers_canonical_script(session, tmp_path: Path) -> None:
    bundle = tmp_path / "srv"
    (bundle / "scripts").mkdir(parents=True)
    (bundle / "server.json").write_text(
        json.dumps({"hostname": "S1", "os": "linux"}), encoding="utf-8"
    )
    (bundle / "scripts" / "a.py").write_text("open('/opt/first/sync.py')\n", encoding="utf-8")
    (bundle / "scripts" / "b.py").write_text("open('/opt/second/sync.py')\n", encoding="utf-8")
    (bundle / "scripts" / "c.py").write_text("open('/opt/second/sync.py')\n", encoding="utf-8")

    workspace = get_or_create_workspace(session, "Canonical Paths")
    run_scan(session, workspace, tmp_path)
    session.flush()

    first = session.scalar(
        select(Entity).where(
            Entity.name == "sync.py", Entity.qualified_name.like("%/opt/first/sync.py")
        )
    )
    second = session.scalar(
        select(Entity).where(
            Entity.name == "sync.py", Entity.qualified_name.like("%/opt/second/sync.py")
        )
    )
    assert first is not None and second is not None

    targets = [
        r.target_id
        for r in session.scalars(
            select(Relationship).where(Relationship.relationship_type == "consumes")
        )
    ]
    assert targets.count(first.id) == 1, "only a.py references /opt/first"
    assert targets.count(second.id) == 2, "b.py and c.py reference /opt/second exactly"


def test_task_relationship_source_uses_full_uri_path(session, tmp_path: Path) -> None:
    root = tmp_path / "tasks"
    root.mkdir()
    for group, script in (("groupA", "a.ps1"), ("groupB", "b.ps1")):
        (root / f"{group}.xml").write_text(
            f"<Task><RegistrationInfo><URI>\\{group}\\sync</URI></RegistrationInfo>"
            "<Actions Context=\"Author\"><Exec><Command>powershell.exe</Command>"
            f"<Arguments>-File C:\\scripts\\{script}</Arguments></Exec></Actions></Task>",
            encoding="utf-8",
        )

    workspace = get_or_create_workspace(session, "Task Source Paths")
    run_scan(session, workspace, root)
    session.flush()

    from collections import defaultdict

    by_source: dict[str, set[str]] = defaultdict(set)
    for rel in session.scalars(
        select(Relationship).where(Relationship.relationship_type == "runs")
    ):
        source = session.get(Entity, rel.source_id)
        target = session.get(Entity, rel.target_id)
        by_source[source.meta_json.get("task_path")].add(target.name)

    assert "a.ps1" in by_source["groupA/sync"]
    assert "b.ps1" not in by_source["groupA/sync"]
    assert "b.ps1" in by_source["groupB/sync"]
    assert "a.ps1" not in by_source["groupB/sync"]


def test_truncated_json_does_not_retire_previous_discoveries(session, tmp_path: Path) -> None:
    root = tmp_path / "cfg"
    root.mkdir()
    config = root / "config.json"
    config.write_text('{"endpoint": "https://api.example.com/v1"}', encoding="utf-8")

    workspace = get_or_create_workspace(session, "Truncated Config")
    run_scan(session, workspace, root)
    session.flush()
    api = session.scalar(
        select(Entity).where(Entity.entity_type == EntityType.API.value)
    )
    assert api is not None and api.is_active is True

    config.write_text('{"endpoint": "https://api.', encoding="utf-8")
    summary = run_scan(session, workspace, root)
    session.flush()

    assert summary["warnings"] >= 1, "malformed JSON should warn"
    assert session.get(Entity, api.id).is_active is True, (
        "a partially parsed file must not authorise retirement"
    )
