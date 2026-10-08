"""Application configuration.

Local-first by default: everything lives under a user-writable directory and
nothing is sent anywhere. Environment variables use the ``ATLAS_`` prefix.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ATLAS_", extra="ignore")

    app_name: str = "Integration Atlas"
    version: str = "0.2.0"

    #: Directory holding the local SQLite database and any local state.
    data_dir: Path = Path.home() / ".integration-atlas"
    database_url: str = ""

    #: Serve the built frontend from this directory when present.
    static_dir: Path = Path(__file__).resolve().parents[2] / "frontend" / "dist"

    #: Root the scanner is allowed to read from. Empty means "any path the
    #: operator explicitly passes on the CLI". See docs/security.md.
    scan_root_allowlist: list[Path] = []

    host: str = "127.0.0.1"
    port: int = 8000

    #: Hard cap on graph payload size to keep the UI responsive.
    max_graph_nodes: int = 2000
    max_file_bytes: int = 4_000_000

    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{(self.data_dir / 'atlas.sqlite3').as_posix()}"


def get_settings() -> Settings:
    return Settings()
