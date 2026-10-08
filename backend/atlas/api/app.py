"""FastAPI application factory.

Serves the JSON API and, when a built frontend exists, the SPA from
``frontend/dist`` so ``atlas serve`` gives a single URL to open.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from atlas import __version__
from atlas.api.routes import entities, graph, risks, scans, workspaces
from atlas.config import get_settings
from atlas.db import init_db


def create_app(*, initialise_db: bool = True) -> FastAPI:
    settings = get_settings()
    if initialise_db:
        init_db()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=(
            "Local-first discovery and impact analysis for enterprise integration estates. "
            "Maps systems, scripts, databases, files and APIs — then shows what could break "
            "when something changes."
        ),
        contact={"name": "Integration Atlas contributors"},
        license_info={"name": "Apache-2.0"},
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(workspaces.router)
    app.include_router(entities.router)
    app.include_router(graph.router)
    app.include_router(risks.router)
    app.include_router(scans.router)

    @app.get("/api/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok", "version": __version__, "app": settings.app_name}

    _mount_frontend(app, settings.static_dir)
    return app


def _mount_frontend(app: FastAPI, static_dir: Path) -> None:
    if not static_dir.is_dir():
        @app.get("/", include_in_schema=False)
        def index() -> JSONResponse:
            return JSONResponse(
                {
                    "name": "Integration Atlas",
                    "message": "Frontend not built. Run `npm --prefix frontend install && npm --prefix frontend run build`, "
                    "or use the Vite dev server on http://localhost:5173.",
                    "api": "/docs",
                }
            )
        return

    assets = static_dir / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    index_file = static_dir / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str, request: Request):  # type: ignore[no-untyped-def]
        if full_path.startswith("api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        candidate = static_dir / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index_file)


app = create_app()
