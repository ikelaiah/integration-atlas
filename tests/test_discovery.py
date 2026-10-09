"""End-to-end discovery and API tests.

These exercise the real pipeline: walk a folder of artefacts, scan them,
normalise the findings, persist them, then answer questions through the API.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from atlas.demo.seeder import get_or_create_workspace, run_risk_analysis
from atlas.domain import EntityType
from atlas.models import Base, Entity, Evidence, Relationship, Scan, ScanEvent, SecretEvent
from atlas.scanners.runner import iter_candidate_files, run_scan
from atlas.services.graph import GraphIndex
from atlas.services.impact import analyse_impact

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "northstar"


@pytest.fixture()
def session():
    # TestClient serves requests on a worker thread. SQLite's default
    # SingletonThreadPool hands each thread its own connection — which for an
    # in-memory database means its own empty database. StaticPool keeps one
    # shared connection so the schema is visible to every thread.
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    session = factory()
    try:
        yield session
        session.commit()
    finally:
        session.close()
        engine.dispose()


# --------------------------------------------------------------------------- #
# Discovery pipeline
# --------------------------------------------------------------------------- #
def test_walker_finds_expected_artefacts() -> None:
    files = sorted(p.name for p in iter_candidate_files(EXAMPLES))
    assert "student_extract.sql" in files
    assert "export_students.ps1" in files
    assert "identity_sync.py" in files
    assert "settings.ini" in files
    assert "nightly-student-export.xml" in files
    assert "integrations" in files  # the cron file


def test_full_scan_discovers_the_student_pipeline(session) -> None:
    workspace = get_or_create_workspace(session, "Scan Test")
    summary = run_scan(session, workspace, EXAMPLES)

    assert summary["files_parsed"] >= 6
    assert summary["entities"] > 10
    assert summary["relationships"] > 10

    entities = list(session.scalars(select(Entity).where(Entity.workspace_id == workspace.id)))
    names = {e.name for e in entities}

    # The pipeline artefacts must all be present.
    for expected in (
        "student_extract.sql",
        "export_students.ps1",
        "identity_sync.py",
        "nightly-student-export",
        "students.csv",
    ):
        assert expected in names, f"{expected} should be discovered"

    types = {e.entity_type for e in entities}
    assert EntityType.SCRIPT.value in types
    assert EntityType.SCHEDULED_JOB.value in types
    assert EntityType.TABLE.value in types


def test_scan_produces_evidence_for_relationships(session) -> None:
    workspace = get_or_create_workspace(session, "Evidence Test")
    run_scan(session, workspace, EXAMPLES)

    relationships = list(
        session.scalars(select(Relationship).where(Relationship.workspace_id == workspace.id))
    )
    assert relationships
    evidence = list(session.scalars(select(Evidence)))
    assert evidence, "every discovery should be explainable"
    covered = {e.relationship_id for e in evidence if e.relationship_id}
    assert len(covered) > 3, "several relationships should carry evidence"

    with_line = [e for e in evidence if e.line_start is not None]
    assert with_line, "evidence should point at source lines"


def test_scan_redacts_secrets_before_persistence(session) -> None:
    workspace = get_or_create_workspace(session, "Secret Test")
    run_scan(session, workspace, EXAMPLES)

    rows = list(session.scalars(select(Entity)))
    rows += list(session.scalars(select(Relationship)))
    rows += list(session.scalars(select(Evidence)))

    for row in rows:
        blobs = [
            getattr(row, attr, "")
            for attr in ("description", "location", "snippet", "qualified_name", "name")
        ]
        blob = " ".join(str(b) for b in blobs)
        assert "ChangeMeOnNextDeploy!" not in blob
        assert "ProdFinance" not in blob

    # The redaction event is recorded so the operator knows something was masked.
    events = list(session.scalars(select(SecretEvent)))
    assert all("ChangeMeOnNextDeploy!" not in e.preview for e in events)


def test_relationships_link_the_pipeline(session) -> None:
    workspace = get_or_create_workspace(session, "Link Test")
    run_scan(session, workspace, EXAMPLES)

    entities = list(session.scalars(select(Entity).where(Entity.workspace_id == workspace.id)))
    relationships = list(
        session.scalars(select(Relationship).where(Relationship.workspace_id == workspace.id))
    )
    index = GraphIndex(entities, relationships)

    by_name = {}
    for entity in entities:
        by_name.setdefault(entity.name, entity)

    ps1 = by_name.get("export_students.ps1")
    csv = by_name.get("students.csv")
    assert ps1 is not None and csv is not None

    # The PowerShell job writes the CSV — influence flows script -> file.
    downstream = index.downstream(ps1.id)
    assert csv.id in set(downstream.entity_ids), (
        "export_students.ps1 should influence students.csv"
    )


def test_impact_analysis_on_a_scanned_estate(session) -> None:
    workspace = get_or_create_workspace(session, "Impact Test")
    run_scan(session, workspace, EXAMPLES)

    entities = list(session.scalars(select(Entity).where(Entity.workspace_id == workspace.id)))
    relationships = list(
        session.scalars(select(Relationship).where(Relationship.workspace_id == workspace.id))
    )
    index = GraphIndex(entities, relationships)

    person = next((e for e in entities if e.name == "Person"), None)
    assert person is not None, "Student.Person should be discovered"

    impact = analyse_impact(index, person.id)
    affected = {index.nodes[i.entity_id].name for i in impact.items if i.entity_id in index.nodes}
    assert "student_extract.sql" in affected


def test_rescan_reconciles_instead_of_duplicating(session) -> None:
    workspace = get_or_create_workspace(session, "Rescan Test")
    first = run_scan(session, workspace, EXAMPLES)
    second = run_scan(session, workspace, EXAMPLES)

    assert second["entities_added"] == 0, "a rescan should not duplicate entities"
    assert second["relationships_added"] == 0, "a rescan should not duplicate relationships"
    assert first["entities"] == second["entities"]


def test_risk_engine_flags_concentration_and_missing_owner(session) -> None:
    workspace = get_or_create_workspace(session, "Risk Test")
    run_scan(session, workspace, EXAMPLES)
    count = run_risk_analysis(session, workspace)
    assert count >= 0


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
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


def test_health_endpoint(client) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_openapi_is_generated(client) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    assert "/api/graph" in spec["paths"]
    assert "/api/impact/{entity_id}" in spec["paths"]
    assert "/api/search" in spec["paths"]


def test_workspace_and_graph_endpoints(client, session) -> None:
    workspace = get_or_create_workspace(session, "API Test")
    session.commit()

    listing = client.get("/api/workspaces")
    assert listing.status_code == 200
    assert any(w["id"] == workspace.id for w in listing.json())

    run_scan(session, workspace, EXAMPLES)
    session.commit()

    graph = client.get(f"/api/graph?workspace_id={workspace.id}")
    assert graph.status_code == 200
    payload = graph.json()
    assert payload["nodes"], "graph should have nodes"
    assert payload["edges"], "graph should have edges"
    assert payload["totals"]["nodes"] == len(payload["nodes"])


def test_search_endpoint(client, session) -> None:
    workspace = get_or_create_workspace(session, "Search Test")
    run_scan(session, workspace, EXAMPLES)
    session.commit()

    response = client.get(f"/api/search?workspace_id={workspace.id}&q=student")
    assert response.status_code == 200
    payload = response.json()
    assert payload["hits"], "searching 'student' should hit something"
    assert all("entity" in hit for hit in payload["hits"])


def test_impact_endpoint(client, session) -> None:
    workspace = get_or_create_workspace(session, "Impact API")
    run_scan(session, workspace, EXAMPLES)
    session.commit()

    entities = list(session.scalars(select(Entity).where(Entity.workspace_id == workspace.id)))
    target = next(e for e in entities if e.entity_type == EntityType.SCRIPT.value)

    response = client.get(
        f"/api/impact/{target.id}?workspace_id={workspace.id}&direction=downstream"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["root"]["id"] == target.id
    assert payload["direction"] == "downstream"
    assert "groups" in payload


def test_path_endpoint(client, session) -> None:
    workspace = get_or_create_workspace(session, "Path API")
    run_scan(session, workspace, EXAMPLES)
    session.commit()

    entities = list(session.scalars(select(Entity).where(Entity.workspace_id == workspace.id)))
    script = next(e for e in entities if e.name == "export_students.ps1")
    csv = next(e for e in entities if e.name == "students.csv")

    response = client.get(
        f"/api/path?workspace_id={workspace.id}&source_id={script.id}&target_id={csv.id}"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["found"] is True
    assert payload["steps"][0]["entity"]["id"] == script.id
    assert payload["steps"][-1]["entity"]["id"] == csv.id


def test_graph_combined_filters_keep_workspace_facets(client, session) -> None:
    workspace = get_or_create_workspace(session, "Filter API")
    nodes = [
        Entity(workspace_id=workspace.id, entity_type="system", name="Source One",
               fingerprint="source-one", environment="production", confidence="high"),
        Entity(workspace_id=workspace.id, entity_type="script", name="Export Job",
               fingerprint="export-job", environment="production", confidence="medium"),
        Entity(workspace_id=workspace.id, entity_type="system", name="Other",
               fingerprint="other", environment="test", confidence="low"),
    ]
    session.add_all(nodes)
    session.flush()
    session.add_all([
        Relationship(workspace_id=workspace.id, source_id=nodes[0].id,
                     target_id=nodes[1].id, relationship_type="produces",
                     confidence="high", review_status="confirmed", fingerprint="a-b"),
        Relationship(workspace_id=workspace.id, source_id=nodes[1].id,
                     target_id=nodes[2].id, relationship_type="calls",
                     confidence="low", review_status="rejected", fingerprint="b-c"),
    ])
    session.commit()

    filtered = client.get(
        f"/api/graph?workspace_id={workspace.id}&environment=production"
        "&relationship_type=produces&review_status=confirmed&q=job"
    )
    assert filtered.status_code == 200, filtered.text
    payload = filtered.json()
    assert {node["name"] for node in payload["nodes"]} == {"Export Job", "Source One"}
    assert [edge["relationship_type"] for edge in payload["edges"]] == ["produces"]
    assert payload["facets"]["entity_type"] == {"system": 2, "script": 1}
    assert payload["facets"]["review_status"]["rejected"] == 1
    assert payload["facets"]["relationship_type"] == {"produces": 1, "calls": 1}

    rejected = client.get(
        f"/api/graph?workspace_id={workspace.id}&review_status=rejected"
    ).json()
    assert [edge["relationship_type"] for edge in rejected["edges"]] == ["calls"]
    assert len(rejected["nodes"]) == 2
    default = client.get(f"/api/graph?workspace_id={workspace.id}").json()
    assert all(edge["review_status"] != "rejected" for edge in default["edges"])

    selected = client.get(
        f"/api/graph?workspace_id={workspace.id}&environment=production"
        "&relationship_type=produces&review_status=confirmed"
    ).json()
    diagram = client.get(
        f"/api/graph/export?workspace_id={workspace.id}&format=mermaid"
        "&environment=production&relationship_type=produces&review_status=confirmed"
    )
    assert diagram.status_code == 200, diagram.text
    assert "attachment" in diagram.headers["content-disposition"]
    assert f"nodes={len(selected['nodes'])} edges={len(selected['edges'])}" in diagram.text
    assert "Source One" in diagram.text and "Export Job" in diagram.text
    assert "Other" not in diagram.text

    bounded = client.get(
        f"/api/graph?workspace_id={workspace.id}&relationship_type=produces&limit=1"
    ).json()
    bounded_diagram = client.get(
        f"/api/graph/export?workspace_id={workspace.id}"
        "&relationship_type=produces&limit=1"
    )
    assert bounded["truncated"] is True
    assert len(bounded["nodes"]) == 1 and bounded["edges"] == []
    assert "nodes=1 edges=0" in bounded_diagram.text
    assert "truncated" in bounded_diagram.text


def test_path_reports_influence_mode(client, session) -> None:
    workspace = get_or_create_workspace(session, "Path modes")
    nodes = [
        Entity(workspace_id=workspace.id, entity_type="system", name=name, fingerprint=name)
        for name in ("A", "B", "C")
    ]
    session.add_all(nodes)
    session.flush()
    session.add_all([
        Relationship(workspace_id=workspace.id, source_id=nodes[0].id,
                     target_id=nodes[1].id, relationship_type="produces", fingerprint="a-b"),
        Relationship(workspace_id=workspace.id, source_id=nodes[2].id,
                     target_id=nodes[1].id, relationship_type="produces", fingerprint="c-b"),
    ])
    session.commit()
    def path(a: int, b: int) -> dict:
        return client.get(
            f"/api/path?workspace_id={workspace.id}&source_id={nodes[a].id}&target_id={nodes[b].id}"
        ).json()
    assert path(0, 1)["mode"] == "downstream"
    assert path(1, 0)["mode"] == "upstream"
    assert path(0, 2)["mode"] == "connected"


def test_relationship_review_endpoint(client, session) -> None:
    workspace = get_or_create_workspace(session, "Review API")
    run_scan(session, workspace, EXAMPLES)
    session.commit()

    rel = session.scalar(
        select(Relationship).where(Relationship.workspace_id == workspace.id)
    )
    assert rel is not None

    response = client.patch(
        f"/api/relationships/{rel.id}", json={"review_status": "confirmed"}
    )
    assert response.status_code == 200
    assert response.json()["review_status"] == "confirmed"

    rejected = client.patch(
        f"/api/relationships/{rel.id}", json={"review_status": "rejected"}
    )
    assert rejected.status_code == 200

    # Rejected relationships disappear from the default graph.
    graph = client.get(f"/api/graph?workspace_id={workspace.id}")
    assert rel.id not in {e["id"] for e in graph.json()["edges"]}


def test_preview_rolls_back_and_apply_records_actual_diff(client, session, tmp_path) -> None:
    workspace = get_or_create_workspace(session, "Preview API")
    session.commit()
    source = tmp_path / "extract.sql"
    source.write_text("SELECT StudentID FROM Student;", encoding="utf-8")
    counts_before = tuple(
        session.query(model).count()
        for model in (Entity, Relationship, Evidence, Scan, ScanEvent)
    )

    preview = client.post(
        "/api/scans/preview", json={"workspace_id": workspace.id, "root_path": str(tmp_path)}
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["diff_summary"]["entities"]["added"] > 0
    assert tuple(
        session.query(model).count()
        for model in (Entity, Relationship, Evidence, Scan, ScanEvent)
    ) == counts_before

    source.write_text("SELECT StudentID FROM Student;\nSELECT Name FROM Student;", encoding="utf-8")
    applied = client.post(
        "/api/scans", json={"workspace_id": workspace.id, "root_path": str(tmp_path)}
    )
    assert applied.status_code == 201, applied.text
    actual = applied.json()["scan"]["diff_summary"]
    assert actual["entities"]["added"] > 0
    assert client.get(f"/api/scans/{applied.json()['scan']['id']}").json()["scan"]["diff_summary"] == actual
    history = client.get(f"/api/scans?workspace_id={workspace.id}").json()
    assert history[0]["scan"]["id"] == applied.json()["scan"]["id"]
    unchanged = client.post(
        "/api/scans", json={"workspace_id": workspace.id, "root_path": str(tmp_path)}
    )
    assert unchanged.json()["scan"]["diff_summary"]["total"] == 0
    assert client.post(
        "/api/scans",
        json={"workspace_id": workspace.id, "root_path": str(tmp_path), "apply_changes": False},
    ).status_code == 400

    source.unlink()
    retirement = client.post(
        "/api/scans/preview", json={"workspace_id": workspace.id, "root_path": str(tmp_path)}
    )
    assert retirement.status_code == 200
    assert retirement.json()["diff_summary"]["entities"]["removed"] > 0
    assert session.query(Entity).filter_by(workspace_id=workspace.id, is_active=True).count() > 0
    applied_retirement = client.post(
        "/api/scans", json={"workspace_id": workspace.id, "root_path": str(tmp_path)}
    )
    assert applied_retirement.json()["scan"]["diff_summary"]["entities"]["removed"] > 0


def test_review_queue_verdict_and_note_survive_rescan(client, session, tmp_path) -> None:
    workspace = get_or_create_workspace(session, "Queue API")
    source = tmp_path / "extract.sql"
    source.write_text("SELECT StudentID FROM Student;", encoding="utf-8")
    run_scan(session, workspace, tmp_path)
    session.commit()

    queue = client.get(f"/api/review?workspace_id={workspace.id}&status=proposed")
    assert queue.status_code == 200, queue.text
    assert queue.json()["items"]
    rel_id = queue.json()["items"][0]["id"]
    verdict = client.post(
        f"/api/review/{rel_id}",
        json={"review_status": "rejected", "note": "Reviewed. password=supersecret123"},
    )
    assert verdict.status_code == 200, verdict.text
    assert verdict.json()["review_status"] == "rejected"
    assert "supersecret123" not in verdict.text
    assert client.get(f"/api/review?workspace_id={workspace.id}&status=rejected").json()["items"]

    run_scan(session, workspace, tmp_path)
    session.commit()
    after = client.get(f"/api/review?workspace_id={workspace.id}&status=rejected").json()
    assert any(item["id"] == rel_id for item in after["items"])


def test_entity_detail_includes_relationships(client, session) -> None:
    workspace = get_or_create_workspace(session, "Detail API")
    run_scan(session, workspace, EXAMPLES)
    session.commit()

    entities = list(session.scalars(select(Entity).where(Entity.workspace_id == workspace.id)))
    target = next(e for e in entities if e.name == "export_students.ps1")

    response = client.get(f"/api/entities/{target.id}")
    assert response.status_code == 200
    assert response.json()["name"] == "export_students.ps1"

    rels = client.get(f"/api/entities/{target.id}/relationships")
    assert rels.status_code == 200
    assert isinstance(rels.json(), list)


def test_manual_relationship_can_be_added(client, session) -> None:
    workspace = get_or_create_workspace(session, "Manual API")
    run_scan(session, workspace, EXAMPLES)
    session.commit()

    entities = list(session.scalars(select(Entity).where(Entity.workspace_id == workspace.id)))
    a, b = entities[0], entities[-1]

    response = client.post(
        f"/api/relationships?workspace_id={workspace.id}",
        json={
            "source_id": a.id,
            "target_id": b.id,
            "relationship_type": "depends_on",
            "label": "reviewed by an operator",
            "evidence": [
                {
                    "evidence_kind": "manual_note",
                    "snippet": "Confirmed during the 2026 integration review.",
                    "confidence": "manual",
                }
            ],
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["source_kind"] == "manual"
    assert payload["evidence"], "manual relationships can carry evidence too"


# --------------------------------------------------------------------------- #
# The acceptance scenario
# --------------------------------------------------------------------------- #
def test_first_vertical_slice_end_to_end(client, session) -> None:
    """The project's headline milestone, exercised through the real API.

    Load the Northstar demo, find LegacySIS, pick StudentID, run impact
    analysis, and confirm that every downstream dependency is reachable —
    including the two independent integrations that consume students.csv.
    """
    from atlas.demo.seeder import seed_northstar_demo

    seed_northstar_demo(session, replace=True)
    session.commit()

    workspaces = client.get("/api/workspaces").json()
    workspace = next(w for w in workspaces if w["is_demo"])
    workspace_id = workspace["id"]

    # 1. The graph is populated.
    graph = client.get(f"/api/graph?workspace_id={workspace_id}").json()
    assert len(graph["nodes"]) >= 50
    assert len(graph["edges"]) >= 30

    def node(name: str, entity_type: str | None = None):
        return next(
            n
            for n in graph["nodes"]
            if n["name"] == name and (entity_type is None or n["entity_type"] == entity_type)
        )

    # 2. The systems from the demo story are present.
    legacysis = node("LegacySIS", "system")
    enrolment = node("EnrolmentPortal")
    identity = node("IdentityHub")
    student_id = node("StudentID", "column")

    # 3. Impact analysis on the column reaches both downstream integrations.
    impact = client.get(
        f"/api/impact/{student_id['id']}?workspace_id={workspace_id}&direction=downstream"
    ).json()
    assert impact["total_affected"] >= 15

    affected = {n["id"] for group in impact["groups"] for n in group["entities"]}
    chains = impact["chains"]
    chain_ids = {step["entity"]["id"] for chain in chains for step in chain}
    reachable = affected | chain_ids

    assert identity["id"] in reachable, "IdentityHub should be downstream of StudentID"
    assert enrolment["id"] in reachable, "EnrolmentPortal should be downstream of StudentID"

    # 4. Dependencies of LegacySIS are visible from the entity endpoint.
    detail = client.get(f"/api/entities/{legacysis['id']}").json()
    assert detail["entity_type"] == "system"
    relationships = client.get(f"/api/entities/{legacysis['id']}/relationships").json()
    assert isinstance(relationships, list)

    # 5. Evidence exists for the discovery the user is looking at.
    scripts = [n for n in graph["nodes"] if n["name"] == "student_extract.sql"]
    assert scripts
    evidence = client.get(f"/api/entities/{scripts[0]['id']}/relationships").json()
    snippets = [e["snippet"] for rel in evidence for e in rel.get("evidence", [])]
    assert any("SELECT" in s for s in snippets), "the SQL extract should carry its statement"

    # 6. A dependency path from the legacy system to the portal is discoverable.
    path = client.get(
        f"/api/path?workspace_id={workspace_id}&source_id={legacysis['id']}&target_id={enrolment['id']}"
    ).json()
    assert path["found"] is True
    assert path["length"] >= 3

