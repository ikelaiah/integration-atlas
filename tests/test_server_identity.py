"""Focused regression tests for the two remaining server-bundle identity bugs.

Bug 1 — different local paths on the same server merged because
:func:`atlas.demo.seeder.fingerprint_entity` reduced both the identity and the
location to their last three path segments.

Bug 2 — a known remote UNC share was marked missing because
:meth:`atlas.scanners.normalise.Normaliser._lookup` applied execution-server
isolation to ``FILE``/``SCRIPT`` references even when they pointed at a shared,
unscoped remote location.

Fixtures are written to isolated temporary directories and an in-memory
database; the real atlas-data database is never touched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from atlas.demo.seeder import (
    fingerprint_entity,
    get_or_create_workspace,
    upgrade_legacy_fingerprints,
)
from atlas.domain import Confidence, EntityType, SourceKind, SubjectKind
from atlas.models import Base, Entity, Evidence, Relationship
from atlas.scanners.base import EntityCandidate
from atlas.scanners.normalise import Normaliser, normalise_path_ref
from atlas.scanners.runner import run_scan
from atlas.scanners.server_bundle import ServerInfo


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


def _bundle(base: Path, host: str, *, os_name: str = "windows") -> Path:
    bundle = base / host
    (bundle / "scripts").mkdir(parents=True)
    (bundle / "server.json").write_text(
        json.dumps({"hostname": host, "os": os_name}), encoding="utf-8"
    )
    return bundle


# --------------------------------------------------------------------------- #
# Bug 1 — distinct local paths on one server must not merge
# --------------------------------------------------------------------------- #
def test_distinct_local_paths_on_one_server_stay_distinct(session, tmp_path: Path) -> None:
    bundle = _bundle(tmp_path, "APP01", os_name="linux")
    (bundle / "scripts" / "copy.ps1").write_text(
        "Get-Content -Path /one/shared/jobs/data.csv\n"
        "Get-Content -Path /two/shared/jobs/data.csv\n",
        encoding="utf-8",
    )

    workspace = get_or_create_workspace(session, "Distinct Local Paths")
    run_scan(session, workspace, tmp_path)
    session.flush()

    files = [
        e
        for e in session.scalars(select(Entity))
        if e.entity_type == EntityType.FILE.value and e.name == "data.csv"
    ]
    local_paths = {f.qualified_name.split("::", 1)[-1] for f in files}
    assert {"/one/shared/jobs/data.csv", "/two/shared/jobs/data.csv"} <= local_paths
    assert len({f.fingerprint for f in files}) == len(files)

    # Both distinct paths are reachable as separate entities from the script.
    runs = list(
        session.scalars(
            select(Relationship).where(Relationship.relationship_type == "consumes")
        )
    )
    targets = {session.get(Entity, r.target_id).qualified_name for r in runs}
    assert "/one/shared/jobs/data.csv" in " ".join(targets)
    assert "/two/shared/jobs/data.csv" in " ".join(targets)


def test_identical_local_paths_on_two_servers_stay_distinct(session, tmp_path: Path) -> None:
    for host in ("APP01", "APP02"):
        bundle = _bundle(tmp_path, host, os_name="linux")
        (bundle / "scripts" / "job.ps1").write_text(
            "Get-Content -Path /opt/shared/jobs/data.csv\n", encoding="utf-8"
        )

    workspace = get_or_create_workspace(session, "Same Path Two Servers")
    run_scan(session, workspace, tmp_path)
    session.flush()

    files = [
        e
        for e in session.scalars(select(Entity))
        if e.entity_type == EntityType.FILE.value and e.name == "data.csv"
    ]
    assert len(files) == 2
    assert {f.meta_json.get("server") for f in files} == {"APP01", "APP02"}


@pytest.mark.parametrize(
    "other",
    [
        "C:/Data/Jobs/data.csv",
        r"c:\data\jobs\data.csv",
        r"C:\Data\Jobs\Data.CSV",
    ],
)
def test_equivalent_windows_path_spellings_reconcile(other: str) -> None:
    canonical = r"C:\Data\Jobs\data.csv"
    first = fingerprint_entity("file", canonical, "data.csv", canonical, scope="APP01", windows=True)
    second = fingerprint_entity("file", other, "data.csv", other, scope="APP01", windows=True)
    assert first == second


def test_windows_path_style_inferred_from_drive_letter() -> None:
    first = fingerprint_entity(
        "file", r"C:\Data\Jobs\data.csv", "data.csv", r"C:\Data\Jobs\data.csv", scope="APP01"
    )
    second = fingerprint_entity(
        "file", "c:/data/jobs/data.csv", "data.csv", "c:/data/jobs/data.csv", scope="APP01"
    )
    assert first == second


def test_linux_paths_differing_only_in_case_stay_distinct() -> None:
    first = fingerprint_entity(
        "file", "/opt/Data/x.csv", "x.csv", "/opt/Data/x.csv", scope="APP01"
    )
    second = fingerprint_entity(
        "file", "/opt/data/x.csv", "x.csv", "/opt/data/x.csv", scope="APP01"
    )
    assert first != second


def test_linux_reference_does_not_match_a_case_distinct_path(session) -> None:
    workspace = get_or_create_workspace(session, "Linux Case Resolution")
    normaliser = Normaliser(session, workspace)
    server = ServerInfo(hostname="LINUX01", os="linux")
    discovered = normaliser.upsert_entity(
        EntityCandidate(
            entity_type=EntityType.FILE,
            name="Data.csv",
            qualified_name="/opt/Data.csv",
            location="/opt/Data.csv",
        ),
        server,
    )

    resolved = normaliser.resolve("/opt/data.csv", EntityType.FILE, server)

    assert resolved is None, "Linux resource references must preserve case"
    missing = normaliser.ensure_missing("/opt/data.csv", EntityType.FILE, server)
    assert missing.id != discovered.id
    assert missing.is_missing is True


def test_linux_references_resolve_to_the_matching_case(session) -> None:
    workspace = get_or_create_workspace(session, "Linux Case Matches")
    normaliser = Normaliser(session, workspace)
    server = ServerInfo(hostname="LINUX01", os="linux")
    upper = normaliser.upsert_entity(
        EntityCandidate(
            entity_type=EntityType.FILE,
            name="Data.csv",
            qualified_name="/opt/Data.csv",
            location="/opt/Data.csv",
        ),
        server,
    )
    lower = normaliser.upsert_entity(
        EntityCandidate(
            entity_type=EntityType.FILE,
            name="data.csv",
            qualified_name="/opt/data.csv",
            location="/opt/data.csv",
        ),
        server,
    )

    assert normaliser.resolve("/opt/Data.csv", EntityType.FILE, server).id == upper.id
    assert normaliser.resolve("/opt/data.csv", EntityType.FILE, server).id == lower.id


def test_unc_resources_on_different_hosts_resolve_separately(session) -> None:
    workspace = get_or_create_workspace(session, "Distinct UNC Hosts")
    normaliser = Normaliser(session, workspace)
    server = ServerInfo(hostname="APP01", os="windows")
    one = normaliser.upsert_entity(
        EntityCandidate(
            entity_type=EntityType.FILE,
            name="report.csv",
            qualified_name="//server-one/share/folder/report.csv",
            location="//server-one/share/folder/report.csv",
        )
    )
    two = normaliser.upsert_entity(
        EntityCandidate(
            entity_type=EntityType.FILE,
            name="report.csv",
            qualified_name="//server-two/share/folder/report.csv",
            location="//server-two/share/folder/report.csv",
        )
    )

    assert one.id != two.id
    assert (
        normaliser.resolve(
            r"\\server-one\share\folder\report.csv", EntityType.FILE, server
        ).id
        == one.id
    )
    assert (
        normaliser.resolve(
            r"\\server-two\share\folder\report.csv", EntityType.FILE, server
        ).id
        == two.id
    )


def test_path_normalisation_preserves_unc_prefix() -> None:
    assert normalise_path_ref(r"\\fileserver\share\data.csv") == "//fileserver/share/data.csv"


def test_unc_fingerprints_keep_remote_host_and_full_path() -> None:
    first = fingerprint_entity(
        "file",
        "//server-one/share/folder/report.csv",
        "report.csv",
        "//server-one/share/folder/report.csv",
    )
    other_host = fingerprint_entity(
        "file",
        "//server-two/share/folder/report.csv",
        "report.csv",
        "//server-two/share/folder/report.csv",
    )
    other_path = fingerprint_entity(
        "file",
        "//server-one/other/folder/report.csv",
        "report.csv",
        "//server-one/other/folder/report.csv",
    )

    assert first != other_host, "UNC host is part of the remote resource identity"
    assert first != other_path, "the full remote path is part of the resource identity"


def test_equivalent_unc_spellings_have_the_same_fingerprint() -> None:
    forward = fingerprint_entity(
        "file",
        "//FILESERVER/share/folder/report.csv",
        "report.csv",
        "//FILESERVER/share/folder/report.csv",
    )
    backslash = fingerprint_entity(
        "file",
        r"\\fileserver\share\folder\report.csv",
        "report.csv",
        r"\\fileserver\share\folder\report.csv",
    )

    assert forward == backslash


def test_windows_drive_letter_is_kept_in_scoped_fingerprint() -> None:
    fingerprint = fingerprint_entity(
        "file", r"C:\Data\x.csv", "x.csv", r"C:\Data\x.csv", scope="APP01", windows=True
    )
    assert "c:/data/x.csv" in fingerprint


def test_repeated_bundle_imports_preserve_ids_and_relationships(
    session, tmp_path: Path
) -> None:
    bundle = _bundle(tmp_path, "APP01", os_name="linux")
    (bundle / "scripts" / "copy.ps1").write_text(
        "Get-Content -Path /one/shared/jobs/data.csv\n"
        "Get-Content -Path /two/shared/jobs/data.csv\n",
        encoding="utf-8",
    )

    workspace = get_or_create_workspace(session, "Repeat Local Paths")
    run_scan(session, workspace, tmp_path)
    session.flush()
    first_entity_ids = {e.id for e in session.scalars(select(Entity))}
    first_rel_ids = {r.id for r in session.scalars(select(Relationship))}

    summary = run_scan(session, workspace, tmp_path)
    session.flush()

    assert summary["entities_added"] == 0
    assert summary["relationships_added"] == 0
    assert {e.id for e in session.scalars(select(Entity))} == first_entity_ids
    assert {r.id for r in session.scalars(select(Relationship))} == first_rel_ids


def test_existing_scoped_database_upgrades_without_losing_knowledge(session) -> None:
    workspace = get_or_create_workspace(session, "Legacy Scoped")
    legacy_fingerprint = "app01|script|apps/sync.ps1|apps/sync.ps1"

    entity = Entity(
        workspace_id=workspace.id,
        entity_type=EntityType.SCRIPT.value,
        name="sync.ps1",
        qualified_name=r"APP01::C:\Apps\sync.ps1",
        location=r"C:\Apps\sync.ps1",
        description="Curated by an operator",
        owner="Data Platform",
        source_kind=SourceKind.MANUAL.value,
        manual_fields_json=["description", "owner"],
        fingerprint=legacy_fingerprint,
        meta_json={"server": "APP01", "server_os": "windows"},
    )
    session.add(entity)
    session.flush()
    entity_id = entity.id
    session.add(
        Evidence(
            workspace_id=workspace.id,
            entity_id=entity_id,
            subject_kind=SubjectKind.ENTITY.value,
            evidence_kind="source_line",
            source_path=r"C:\Apps\sync.ps1",
            snippet="discovered sync.ps1",
        )
    )
    session.flush()

    changed = upgrade_legacy_fingerprints(session, workspace_id=workspace.id)
    session.flush()
    assert changed >= 1

    refreshed = session.get(Entity, entity_id)
    assert refreshed.fingerprint != legacy_fingerprint
    assert refreshed.description == "Curated by an operator"
    assert refreshed.owner == "Data Platform"
    assert refreshed.source_kind == SourceKind.MANUAL.value
    assert list(
        session.scalars(select(Evidence).where(Evidence.entity_id == entity_id))
    ), "evidence must survive the upgrade"

    # Idempotent: a second migration is a no-op.
    assert upgrade_legacy_fingerprints(session, workspace_id=workspace.id) == 0

    # A rescan reconciles to the same row instead of duplicating it.
    normaliser = Normaliser(session, workspace)
    result = normaliser.upsert_entity(
        EntityCandidate(
            entity_type=EntityType.SCRIPT,
            name="sync.ps1",
            qualified_name=r"C:\Apps\sync.ps1",
            location=r"C:\Apps\sync.ps1",
        ),
        ServerInfo(hostname="APP01", os="windows"),
    )
    session.flush()

    assert result.id == entity_id
    assert session.get(Entity, entity_id).description == "Curated by an operator"
    duplicates = [
        e
        for e in session.scalars(select(Entity))
        if e.entity_type == EntityType.SCRIPT.value and e.name == "sync.ps1"
    ]
    assert len(duplicates) == 1


# --------------------------------------------------------------------------- #
# Bug 2 — known remote files must not be marked missing
# --------------------------------------------------------------------------- #
def test_known_unc_share_resolves_from_two_servers_to_one_entity(session) -> None:
    workspace = get_or_create_workspace(session, "UNC Shared")
    normaliser = Normaliser(session, workspace)
    shared = normaliser.upsert_entity(
        EntityCandidate(
            entity_type=EntityType.FILE,
            name="students.csv",
            qualified_name=r"\\fileserver\share\students.csv",
            location=r"\\fileserver\share\students.csv",
            technology="UNC",
            confidence=Confidence.HIGH,
            meta={"discovered": True},
        )
    )
    session.flush()
    shared_id = shared.id
    assert shared.is_missing is False

    for host in ("APP01", "APP02"):
        other = Normaliser(session, workspace)
        resolved = other.resolve(
            r"\\fileserver\share\students.csv",
            EntityType.FILE,
            ServerInfo(hostname=host, os="windows"),
        )
        assert resolved is not None
        assert resolved.id == shared_id

    assert (
        len([e for e in session.scalars(select(Entity)) if e.name == "students.csv"]) == 1
    )


def test_ensure_missing_does_not_downgrade_a_discovered_entity(session) -> None:
    workspace = get_or_create_workspace(session, "UNC No Downgrade")
    normaliser = Normaliser(session, workspace)
    shared = normaliser.upsert_entity(
        EntityCandidate(
            entity_type=EntityType.FILE,
            name="students.csv",
            qualified_name=r"\\fileserver\share\students.csv",
            location=r"\\fileserver\share\students.csv",
            technology="UNC",
            confidence=Confidence.HIGH,
            meta={"discovered": True},
        )
    )
    session.flush()
    shared_id = shared.id

    # Even if a placeholder reaches upsert (e.g. a reference spelling the
    # canonical lookup could not see), it must never overwrite the discovery.
    normaliser.upsert_entity(
        EntityCandidate(
            entity_type=EntityType.FILE,
            name="students.csv",
            qualified_name=r"\\fileserver\share\students.csv",
            location=r"\\fileserver\share\students.csv",
            description="Referenced but not discovered.",
            confidence=Confidence.LOW,
            is_missing=True,
        ),
        ServerInfo(hostname="APP01", os="windows"),
    )
    session.flush()

    refreshed = session.get(Entity, shared_id)
    assert refreshed.is_missing is False
    assert refreshed.confidence == Confidence.HIGH.value
    assert refreshed.technology == "UNC"
    assert refreshed.meta_json.get("discovered") is True
    assert refreshed.description != "Referenced but not discovered."


def test_known_unc_share_survives_an_end_to_end_two_server_scan(
    session, tmp_path: Path
) -> None:
    for host in ("APP01", "APP02"):
        bundle = _bundle(tmp_path, host, os_name="windows")
        (bundle / "scripts" / "copy.ps1").write_text(
            r"Get-Content \\fileserver\share\students.csv" + "\n",
            encoding="utf-8",
        )

    workspace = get_or_create_workspace(session, "UNC Two Servers Scan")
    run_scan(session, workspace, tmp_path)
    run_scan(session, workspace, tmp_path)
    session.flush()

    shared = [
        e
        for e in session.scalars(select(Entity))
        if e.entity_type == EntityType.FILE.value and e.name == "students.csv"
    ]
    assert len(shared) == 1, "the shared UNC file must not merge-and-downgrade"
    assert shared[0].is_missing is False
    assert not shared[0].meta_json.get("server")

    targets = {
        session.get(Entity, r.target_id).name
        for r in session.scalars(
            select(Relationship).where(Relationship.relationship_type == "depends_on")
        )
    }
    assert "students.csv" in targets


@pytest.mark.parametrize(
    "discovered,reference",
    [
        (r"\\fileserver\share\students.csv", "//fileserver/share/students.csv"),
        (r"\\FILESERVER\SHARE\students.csv", r"\\fileserver\share\students.csv"),
        (r"//fileserver/share/students.csv", r"\\fileserver\share\students.csv"),
    ],
)
def test_equivalent_unc_spellings_resolve(session, discovered: str, reference: str) -> None:
    workspace = get_or_create_workspace(session, "UNC Spellings")
    normaliser = Normaliser(session, workspace)
    shared = normaliser.upsert_entity(
        EntityCandidate(
            entity_type=EntityType.FILE,
            name="students.csv",
            qualified_name=discovered,
            location=discovered,
            technology="UNC",
        )
    )
    session.flush()

    resolved = normaliser.resolve(
        reference, EntityType.FILE, ServerInfo(hostname="APP01", os="windows")
    )
    assert resolved is not None
    assert resolved.id == shared.id
    assert (
        len([e for e in session.scalars(select(Entity)) if e.name == "students.csv"]) == 1
    )


def test_unknown_remote_reference_creates_shared_placeholder(session) -> None:
    workspace = get_or_create_workspace(session, "Unknown Remote")
    normaliser = Normaliser(session, workspace)
    placeholder = normaliser.ensure_missing(
        r"\\unknown\share\missing.csv",
        EntityType.FILE,
        ServerInfo(hostname="APP01", os="windows"),
    )
    session.flush()

    assert placeholder.is_missing is True
    assert not placeholder.meta_json.get("server"), "remote placeholders are shared"


def test_unknown_local_reference_creates_server_scoped_placeholder(session) -> None:
    workspace = get_or_create_workspace(session, "Unknown Local")
    normaliser = Normaliser(session, workspace)
    placeholder = normaliser.ensure_missing(
        r"C:\scripts\missing.ps1",
        EntityType.SCRIPT,
        ServerInfo(hostname="APP01", os="windows"),
    )
    session.flush()

    assert placeholder.is_missing is True
    assert placeholder.meta_json.get("server") == "APP01"


def test_server_b_cannot_borrow_server_a_local_script(session) -> None:
    workspace = get_or_create_workspace(session, "Local Isolation")
    normaliser = Normaliser(session, workspace)
    a_script = normaliser.upsert_entity(
        EntityCandidate(
            entity_type=EntityType.SCRIPT,
            name="shared.ps1",
            qualified_name=r"C:\scripts\shared.ps1",
            location=r"C:\scripts\shared.ps1",
        ),
        ServerInfo(hostname="SERVER-A", os="windows"),
    )
    session.flush()

    server_b = ServerInfo(hostname="SERVER-B", os="windows")
    assert (
        normaliser.resolve(r"C:\scripts\shared.ps1", EntityType.SCRIPT, server_b) is None
    )
    placeholder = normaliser.ensure_missing(
        r"C:\scripts\shared.ps1", EntityType.SCRIPT, server_b
    )
    session.flush()

    assert placeholder.id != a_script.id
    assert placeholder.meta_json.get("server") == "SERVER-B"


def test_distinct_remote_paths_do_not_merge_through_basename_fallback(session) -> None:
    workspace = get_or_create_workspace(session, "Remote Basenames")
    normaliser = Normaliser(session, workspace)
    first = normaliser.upsert_entity(
        EntityCandidate(
            entity_type=EntityType.FILE,
            name="students.csv",
            qualified_name=r"\\fileserver\share\a\students.csv",
            location=r"\\fileserver\share\a\students.csv",
        )
    )
    second = normaliser.upsert_entity(
        EntityCandidate(
            entity_type=EntityType.FILE,
            name="students.csv",
            qualified_name=r"\\fileserver\share\b\students.csv",
            location=r"\\fileserver\share\b\students.csv",
        )
    )
    session.flush()
    assert first.id != second.id

    resolved = normaliser.resolve(
        r"\\fileserver\share\a\students.csv", EntityType.FILE
    )
    assert resolved is not None and resolved.id == first.id

    # A reference to neither known path must not fall back to a basename match.
    assert (
        normaliser.resolve(r"\\fileserver\share\c\students.csv", EntityType.FILE)
        is None
    )
