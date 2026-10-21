"""Workspace isolation from the Northstar demo (v0.6.0).

Scans never write into the demo workspace, previews never create workspaces,
and resetting the demo never deletes data that did not come from the demo.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from atlas.demo.seeder import DEMO_SLUG, find_demo_workspace, seed_northstar_demo
from atlas.models import Base, Entity, Relationship, Scan, Workspace
from atlas.scanners.runner import run_scan

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "multi-server" / "windows-app01"


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False, future=True)()
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


def _count(session, model, workspace_id: str) -> int:
    return len(list(session.scalars(select(model.id).where(model.workspace_id == workspace_id))))


def _demo(client) -> dict:
    response = client.post("/api/demo/reset")
    assert response.status_code == 200, response.text
    return response.json()


def test_first_run_has_no_workspace_until_one_is_chosen(client) -> None:
    assert client.get("/api/workspaces").json() == []
    status = client.get("/api/demo").json()
    assert status["workspace"] is None
    assert status["demo_entities"] == 95
    assert status["has_other_data"] is False


def test_scans_cannot_target_the_demo_workspace(client, session) -> None:
    demo_id = _demo(client)["workspace_id"]
    before = _count(session, Entity, demo_id)

    for path, body in (
        ("/api/scans/preview", {"root_path": str(EXAMPLE), "workspace_id": demo_id}),
        ("/api/scans", {"root_path": str(EXAMPLE), "workspace_id": demo_id}),
        ("/api/scans", {"root_path": str(EXAMPLE), "workspace_id": DEMO_SLUG}),
        ("/api/scans", {"root_path": str(EXAMPLE), "workspace_name": "Northstar Education Group"}),
    ):
        response = client.post(path, json=body)
        assert response.status_code == 409, (path, body, response.text)
        assert "demo workspace" in response.json()["detail"]

    assert _count(session, Entity, demo_id) == before
    assert _count(session, Scan, demo_id) == 0


def test_preview_into_a_new_workspace_creates_nothing(client, session) -> None:
    _demo(client)
    workspaces_before = client.get("/api/workspaces").json()

    preview = client.post(
        "/api/scans/preview", json={"root_path": str(EXAMPLE), "workspace_name": "App01 estate"}
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["workspace_name"] == "App01 estate"
    assert body["creates_workspace"] is True
    assert body["diff_summary"]["entities"]["added"] > 0
    assert client.get("/api/workspaces").json() == workspaces_before

    applied = client.post(
        "/api/scans", json={"root_path": str(EXAMPLE), "workspace_name": "App01 estate"}
    )
    assert applied.status_code == 201, applied.text
    workspace_id = applied.json()["scan"]["workspace_id"]
    created = session.get(Workspace, workspace_id)
    assert created.name == "App01 estate" and created.is_demo is False
    assert _count(session, Entity, workspace_id) > 0

    # A second preview into the same workspace reuses it.
    again = client.post(
        "/api/scans/preview", json={"root_path": str(EXAMPLE), "workspace_id": workspace_id}
    ).json()
    assert again["creates_workspace"] is False


def test_regular_workspace_cannot_take_the_demo_name(client) -> None:
    _demo(client)
    response = client.post("/api/workspaces", json={"name": "Northstar Education Group"})
    assert response.status_code == 409
    assert client.post("/api/workspaces", json={"name": "   "}).status_code == 422
    created = client.post("/api/workspaces", json={"name": "Finance"})
    assert created.status_code == 200
    assert created.json()["is_demo"] is False


def test_reset_restores_a_demo_that_only_holds_demo_edits(client, session) -> None:
    demo_id = _demo(client)["workspace_id"]
    entity = session.scalar(
        select(Entity).where(Entity.workspace_id == demo_id, Entity.name == "LegacySIS")
    )
    original_owner = entity.owner
    assert client.patch(f"/api/entities/{entity.id}", json={"owner": "Someone else"}).status_code == 200
    rel = session.scalar(
        select(Relationship).where(
            Relationship.workspace_id == demo_id, Relationship.review_status == "proposed"
        )
    )
    assert client.post(f"/api/review/{rel.id}", json={"review_status": "rejected"}).status_code == 200

    status = client.get("/api/demo").json()
    assert status["workspace"]["id"] == demo_id
    assert status["edited_entities"] == 1
    assert status["reviewed_relationships"] == 1
    assert status["has_other_data"] is False
    assert status["kept_workspace_name"] is None

    result = _demo(client)
    assert result["workspace_id"] == demo_id
    assert result["kept_workspace_id"] is None
    session.expire_all()
    restored = session.scalar(
        select(Entity).where(Entity.workspace_id == demo_id, Entity.name == "LegacySIS")
    )
    assert restored.owner == original_owner
    assert [w["id"] for w in client.get("/api/workspaces").json()] == [demo_id]


def test_reset_keeps_scan_results_found_in_the_demo_workspace(client, session) -> None:
    """Databases from before v0.6.0 may hold scans inside the demo workspace."""
    demo_id = _demo(client)["workspace_id"]
    demo = session.get(Workspace, demo_id)
    run_scan(session, demo, EXAMPLE)  # bypasses the API guard, as older releases did
    session.commit()
    mixed_entities = _count(session, Entity, demo_id)
    assert mixed_entities > 95

    status = client.get("/api/demo").json()
    assert status["scans"] == 1
    assert status["other_entities"] == mixed_entities - 95
    assert status["has_other_data"] is True
    assert status["kept_workspace_name"].startswith("Northstar Education Group (kept ")

    result = _demo(client)
    session.expire_all()
    kept = session.get(Workspace, demo_id)
    assert result["kept_workspace_id"] == demo_id
    assert result["kept_workspace_name"] == kept.name
    assert kept.is_demo is False and kept.slug != DEMO_SLUG
    assert _count(session, Entity, demo_id) == mixed_entities
    assert _count(session, Scan, demo_id) == 1

    fresh = find_demo_workspace(session)
    assert fresh.id == result["workspace_id"] != demo_id
    assert fresh.slug == DEMO_SLUG
    assert _count(session, Entity, fresh.id) == 95
    assert _count(session, Scan, fresh.id) == 0
    assert client.get("/api/demo").json()["has_other_data"] is False


def test_deprecated_seed_route_uses_the_safe_reset(client, session) -> None:
    demo_id = _demo(client)["workspace_id"]
    run_scan(session, session.get(Workspace, demo_id), EXAMPLE)
    session.commit()
    response = client.post("/api/workspaces/anything/seed-demo")
    assert response.status_code == 200
    assert response.json()["kept_workspace_id"] == demo_id


def test_demo_seed_does_not_reuse_a_regular_workspace_with_the_demo_slug(session) -> None:
    regular = Workspace(name="Northstar Education Group", slug=DEMO_SLUG, is_demo=False)
    session.add(regular)
    session.flush()
    result = seed_northstar_demo(session, replace=True)
    assert result.workspace_id != regular.id
    assert find_demo_workspace(session).slug == f"{DEMO_SLUG}-2"
    assert _count(session, Entity, regular.id) == 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
@pytest.fixture()
def cli(tmp_path: Path, monkeypatch):
    from typer.testing import CliRunner

    from atlas import db as atlas_db
    from atlas.cli import app

    monkeypatch.setenv("ATLAS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ATLAS_DATABASE_URL", f"sqlite:///{(tmp_path / 'atlas.db').as_posix()}")
    atlas_db.reset_engine()
    runner = CliRunner()

    def invoke(*args: str):
        result = runner.invoke(app, list(args))
        stderr = getattr(result, "stderr", "") if result.stderr_bytes is not None else ""
        return result, result.output + stderr

    yield invoke
    atlas_db.reset_engine()


def test_cli_scan_refuses_demo_and_names_fallback_workspace(cli) -> None:
    result, _ = cli("demo")
    assert result.exit_code == 0, result.output

    result, output = cli("scan", "run", str(EXAMPLE), "--workspace", DEMO_SLUG)
    assert result.exit_code == 1
    assert "demo workspace" in output

    result, output = cli("scan", "run", str(EXAMPLE), "--workspace", "App01")
    assert result.exit_code == 0, output
    assert "App01" in output

    # The id or slug of an existing workspace selects it instead of creating one.
    result, output = cli("scan", "run", str(EXAMPLE), "--workspace", "app01")
    assert result.exit_code == 0, output
    result, output = cli("status")
    assert output.count("app01") == 1

    result, output = cli("impact", "LegacySIS")
    assert result.exit_code == 0, output
    assert "Using workspace" in output and "Northstar Education Group" in output
