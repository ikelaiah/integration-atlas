"""``atlas`` command-line interface.

Designed to be useful on its own: seed a demo, scan a folder, inspect the
estate, run impact analysis and export — without ever opening a browser.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from sqlalchemy import select

from atlas import __version__
from atlas.config import get_settings
from atlas.db import init_db, session_scope
from atlas.demo.seeder import demo_entity_count, seed_northstar_demo
from atlas.domain import EntityType
from atlas.models import Entity, Relationship, Workspace

app = typer.Typer(
    name="atlas",
    help="Integration Atlas — map your integration estate, then see what could break.",
    add_completion=True,
    no_args_is_help=True,
)
scan_app = typer.Typer(help="Discover integrations from filesystem artefacts.")
app.add_typer(scan_app, name="scan")

console = Console()
err_console = Console(stderr=True)

MOTTO = "Map the systems you inherited before you change the systems you inherited."


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"[bold]Integration Atlas[/bold] {__version__}")
        raise typer.Exit()


@app.callback()
def root(
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=_version_callback, is_eager=True),
    ] = None,
) -> None:
    """Integration Atlas CLI."""


@app.command()
def init() -> None:
    """Create the local database and data directory."""
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    init_db()
    console.print(
        Panel.fit(
            f"[bold green]Initialised[/bold green]\n\n"
            f"Data directory  [cyan]{settings.data_dir}[/cyan]\n"
            f"Database        [cyan]{settings.resolved_database_url()}[/cyan]\n"
            f"Next step       [white]atlas demo[/white]  or  [white]atlas scan ./integrations[/white]",
            title="Integration Atlas",
            subtitle=MOTTO,
            border_style="cyan",
        )
    )


@app.command()
def demo(
    reset: Annotated[bool, typer.Option("--reset", help="Replace existing demo data.")] = True,
) -> None:
    """Load the Northstar Education Group demo estate."""
    init_db()
    entity_total, rel_total = demo_entity_count()
    with session_scope() as session:
        result = seed_northstar_demo(session, replace=reset)

    console.print(
        Panel.fit(
            f"[bold green]Northstar Education Group[/bold green] seeded\n\n"
            f"Entities        [cyan]{entity_total}[/cyan]\n"
            f"Relationships   [cyan]{rel_total}[/cyan]\n"
            f"Evidence rows   [cyan]{result.evidence_added}[/cyan]\n"
            f"Risks flagged   [yellow]{result.risks_found}[/yellow]\n\n"
            f"Open the app with [white]atlas serve[/white], then explore the Atlas tab.",
            title="Demo loaded",
            border_style="green",
        )
    )


@app.command()
def serve(
    host: Annotated[str, typer.Option("--host", help="Bind address.")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port", help="Port.")] = 8000,
    reload: Annotated[bool, typer.Option("--reload", help="Auto-reload (development).")] = False,
) -> None:
    """Start the local web application."""
    import uvicorn

    init_db()
    url = f"http://{host}:{port}"
    console.print(
        Panel.fit(
            f"[bold green]Integration Atlas[/bold green] is running\n\n"
            f"Application   [cyan]{url}[/cyan]\n"
            f"API docs      [cyan]{url}/docs[/cyan]\n\n"
            f"Press [white]Ctrl+C[/white] to stop.",
            title="atlas serve",
            border_style="cyan",
        )
    )
    uvicorn.run("atlas.api.app:app", host=host, port=port, reload=reload)


@app.command()
def status() -> None:
    """Show workspaces and estate totals."""
    init_db()
    with session_scope() as session:
        workspaces = list(session.scalars(select(Workspace).order_by(Workspace.created_at)))
        if not workspaces:
            console.print(
                Panel.fit(
                    "No workspaces yet.\n\n"
                    "Load the demo with [white]atlas demo[/white]\n"
                    "or discover from disk with [white]atlas scan ./integrations[/white]",
                    title="Empty",
                    border_style="dim",
                )
            )
            return

        table = Table(title="Workspaces", show_header=True, header_style="bold cyan")
        table.add_column("Name", style="white")
        table.add_column("Slug", style="dim")
        table.add_column("Entities", justify="right")
        table.add_column("Relationships", justify="right")
        table.add_column("Demo", justify="center")

        for workspace in workspaces:
            entity_count = len(
                list(session.scalars(select(Entity).where(Entity.workspace_id == workspace.id)))
            )
            rel_count = len(
                list(
                    session.scalars(
                        select(Relationship).where(Relationship.workspace_id == workspace.id)
                    )
                )
            )
            table.add_row(
                workspace.name,
                workspace.slug,
                str(entity_count),
                str(rel_count),
                "yes" if workspace.is_demo else "no",
            )
        console.print(table)


@app.command()
def impact(
    entity: Annotated[str, typer.Argument(help="Entity name, qualified name or id.")],
    workspace: Annotated[
        str | None, typer.Option("--workspace", "-w", help="Workspace slug or id.")
    ] = None,
    depth: Annotated[int | None, typer.Option("--depth", "-d", help="Maximum depth.")] = None,
    direction: Annotated[
        str, typer.Option("--direction", help="downstream or upstream.")
    ] = "downstream",
    as_json: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = False,
) -> None:
    """Show what could break if an entity changes."""
    init_db()
    from atlas.services.graph import GraphIndex
    from atlas.services.impact import analyse_impact

    with session_scope() as session:
        ws = _resolve_workspace(session, workspace)
        if ws is None:
            err_console.print("[red]No workspace found. Try `atlas demo` first.[/red]")
            raise typer.Exit(1)

        entities = list(session.scalars(select(Entity).where(Entity.workspace_id == ws.id)))
        match = _find_entity(entities, entity)
        if match is None:
            err_console.print(f"[red]Entity not found:[/red] {entity}")
            raise typer.Exit(1)

        relationships = list(
            session.scalars(select(Relationship).where(Relationship.workspace_id == ws.id))
        )
        index = GraphIndex(entities, relationships)
        result = analyse_impact(index, match.id, direction=direction, max_depth=depth)

        if as_json:
            from atlas.api.serialisers import node_dict

            payload = {
                "root": node_dict(match),
                "direction": direction,
                "max_depth": depth,
                "total_affected": result.total,
                "affected": [
                    {
                        "id": item.entity_id,
                        "name": index.nodes[item.entity_id].name,
                        "type": index.nodes[item.entity_id].entity_type,
                        "depth": item.depth,
                    }
                    for item in result.items
                    if item.entity_id in index.nodes
                ],
            }
            console.print_json(json.dumps(payload))
            return

        counts = result.counts_by_type(index)
        lines = [
            Text(f"Impact analysis — {match.name}", style="bold white"),
            Text(""),
            Text(f"Direction       {direction}", style="dim"),
            Text(f"Total affected  {result.total}", style="bold"),
            Text(""),
        ]
        for etype, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(Text(f"  {EntityType(etype).label:<18} {count}"))

        if result.items:
            lines.append(Text(""))
            lines.append(Text("Affected:", style="bold"))
            for item in result.items[:40]:
                node = index.nodes.get(item.entity_id)
                if node is None:
                    continue
                lines.append(
                    Text(f"  {'  ' * item.depth}{'└─ ' if item.depth else ''}{node.name}")
                )

        console.print(Panel(Group(*lines), title="Impact", border_style="magenta"))


@app.command()
def export(
    output: Annotated[Path, typer.Option("--out", "-o", help="Output file.")] = Path(
        "atlas-export.json"
    ),
    fmt: Annotated[str, typer.Option("--format", "-f", help="json|csv|graphml")] = "json",
    workspace: Annotated[
        str | None, typer.Option("--workspace", "-w", help="Workspace slug or id.")
    ] = None,
) -> None:
    """Export the discovered model."""
    from atlas.services.exporters import export_workspace

    init_db()
    with session_scope() as session:
        ws = _resolve_workspace(session, workspace)
        if ws is None:
            err_console.print("[red]No workspace found.[/red]")
            raise typer.Exit(1)
        path = export_workspace(session, ws, output, fmt=fmt)
    console.print(f"[green]Exported[/green] {fmt} → [cyan]{path}[/cyan]")


@scan_app.callback(invoke_without_command=True)
def scan_root(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        console.print("[dim]Usage: atlas scan <path> [--workspace NAME][/dim]")


@scan_app.command("run")
def scan_run(
    path: Annotated[Path, typer.Argument(help="Directory to discover.")],
    workspace: Annotated[
        str | None, typer.Option("--workspace", "-w", help="Workspace name or id.")
    ] = None,
) -> None:
    """Discover integrations from a folder of artefacts."""
    from atlas.scanners.runner import run_scan

    root = path.expanduser().resolve()
    if not root.is_dir():
        err_console.print(f"[red]Not a directory:[/red] {root}")
        raise typer.Exit(1)

    init_db()
    from atlas.demo.seeder import get_or_create_workspace

    with session_scope() as session:
        ws = get_or_create_workspace(session, workspace or root.name, description=f"Scanned {root}")
        with console.status(f"[cyan]Scanning {root}...[/cyan]"):
            summary = run_scan(session, ws, root)

    table = Table(title="Scan complete", show_header=True, header_style="bold cyan")
    table.add_column("Metric", style="white")
    table.add_column("Value", justify="right", style="cyan")
    for key, value in summary.items():
        if isinstance(value, (int, str)):
            table.add_row(key.replace("_", " ").title(), str(value))
    console.print(table)


def _resolve_workspace(session, ref: str | None) -> Workspace | None:
    if ref:
        return session.scalar(
            select(Workspace).where((Workspace.id == ref) | (Workspace.slug == ref))
        )
    return session.scalar(select(Workspace).order_by(Workspace.created_at))


def _find_entity(entities: list[Entity], ref: str) -> Entity | None:
    lowered = ref.lower()
    for entity in entities:
        if entity.id == ref:
            return entity
    for entity in entities:
        if (entity.qualified_name or "").lower() == lowered or entity.name.lower() == lowered:
            return entity
    for entity in entities:
        if lowered in (entity.qualified_name or "").lower() or lowered in entity.name.lower():
            return entity
    return None


def main() -> None:
    app()


if __name__ == "__main__":
    main()
