"""Per-server discovery bundles.

Enterprise schedulers are frequently collected machine by machine. A *bundle*
is a directory that ships the scheduler export for one host alongside a small
``server.json`` manifest naming the execution host::

    bundle/
      server.json                 # execution-server manifest
      windows/tasks/*.xml         # Task Scheduler exports (Windows)
      linux/cron.d/*              # system crontabs          (Linux)
      linux/crontabs/<user>       # per-user crontabs        (Linux)
      scripts/*.ps1               # local scripts referenced by the jobs

The manifest is intentionally minimal::

    {
      "hostname": "APP-SERVER-01",
      "fqdn": "app-server-01.corp.example",
      "os": "windows",
      "environment": "production"
    }

Only ``hostname`` is required. The bundle exists so that Atlas can attribute
the jobs and local scripts it finds to the machine that executes them, without
ever inferring that from a task's ``Author``, ``UserId``, ``URI`` or a hostname
that merely appears in a command. Collection only reads and exports artefacts;
nothing discovered is ever executed.

This module contains only pure functions over the filesystem. Persistence and
identity scoping live in :mod:`atlas.scanners.normalise`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from atlas.scanners.base import SKIP_DIRS, read_text_safe

MANIFEST_NAME = "server.json"


@dataclass(frozen=True)
class ServerInfo:
    """The execution server declared by a bundle manifest."""

    hostname: str
    fqdn: str = ""
    os: str = ""
    environment: str = ""
    #: Absolute path of the manifest that declared this server.
    source_path: str = ""
    #: Absolute directory that owns this manifest (and everything below it).
    bundle_dir: str = ""

    @property
    def scope(self) -> str:
        return self.hostname.strip().lower()


def parse_manifest(data: object) -> ServerInfo | None:
    """Build a :class:`ServerInfo` from raw manifest JSON, or ``None`` if invalid."""
    if not isinstance(data, dict):
        return None
    hostname = str(data.get("hostname") or "").strip()
    if not hostname:
        return None
    return ServerInfo(
        hostname=hostname,
        fqdn=str(data.get("fqdn") or "").strip(),
        os=str(data.get("os") or "").strip(),
        environment=str(data.get("environment") or "").strip(),
    )


def discover_server_bundles(root: Path | str) -> list[ServerInfo]:
    """Find every ``server.json`` manifest under ``root`` (nested allowed)."""
    root_path = Path(str(root)).resolve()
    bundles: list[ServerInfo] = []
    stack = [root_path]
    while stack:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            continue
        manifest = next((e for e in entries if e.is_file() and e.name == MANIFEST_NAME), None)
        if manifest is not None:
            text = read_text_safe(manifest)
            info: ServerInfo | None = None
            if text is not None:
                try:
                    info = parse_manifest(json.loads(text))
                except (ValueError, TypeError):
                    info = None
            if info is not None:
                source = str(manifest).replace("\\", "/")
                bundle_dir = str(current).replace("\\", "/")
                bundles.append(
                    ServerInfo(
                        hostname=info.hostname,
                        fqdn=info.fqdn,
                        os=info.os,
                        environment=info.environment,
                        source_path=source,
                        bundle_dir=bundle_dir,
                    )
                )
        for entry in entries:
            if not entry.is_dir():
                continue
            if entry.name.lower() in SKIP_DIRS or entry.name.startswith("."):
                continue
            stack.append(entry)
    return bundles


def server_for_path(path: Path | str, bundles: list[ServerInfo]) -> ServerInfo | None:
    """Return the innermost bundle that owns ``path``, if any."""
    if not bundles:
        return None
    target = str(Path(str(path)).resolve()).replace("\\", "/")
    best: ServerInfo | None = None
    best_len = -1
    for bundle in bundles:
        base = bundle.bundle_dir.rstrip("/")
        if (target == base or target.startswith(base + "/")) and len(base) > best_len:
            best, best_len = bundle, len(base)
    return best
