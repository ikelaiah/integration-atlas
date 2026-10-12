from __future__ import annotations

from pathlib import Path

import pytest


def _frontend_client(static_dir: Path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from atlas.api.app import _mount_frontend

    app = FastAPI()
    _mount_frontend(app, static_dir)
    return TestClient(app)


def test_spa_fallback_does_not_serve_encoded_parent_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_DATA_DIR", str(tmp_path / "data"))
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text("frontend shell", encoding="utf-8")
    (tmp_path / "marker.txt").write_text("outside marker", encoding="utf-8")

    with _frontend_client(frontend) as client:
        response = client.get("/%2e%2e/marker.txt")

    assert response.status_code == 200
    assert response.text == "frontend shell"
    assert "outside marker" not in response.text


def test_spa_fallback_does_not_serve_symlink_outside_frontend(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_DATA_DIR", str(tmp_path / "data"))
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text("frontend shell", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside marker", encoding="utf-8")
    link = frontend / "outside.txt"
    try:
        link.symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"file symlinks are unavailable: {exc}")

    with _frontend_client(frontend) as client:
        response = client.get("/outside.txt")

    assert response.status_code == 200
    assert response.text == "frontend shell"
    assert "outside marker" not in response.text
