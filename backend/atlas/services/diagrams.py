"""Safe, deterministic text diagrams for graph sharing."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from html import escape

from atlas.services.redaction import redact


@dataclass(frozen=True)
class DiagramNode:
    id: str
    name: str
    entity_type: str


@dataclass(frozen=True)
class DiagramEdge:
    from_id: str
    to_id: str
    relationship_type: str


def _alias(identifier: str) -> str:
    return "n_" + sha256(identifier.encode("utf-8")).hexdigest()[:16]


def _label(value: str) -> str:
    # A source name must remain a single quoted diagram label, never a
    # second statement or directive. Redact again at the export boundary.
    flattened = " ".join(redact(value).text.split())[:160]
    return escape(flattened, quote=True).replace("|", "&#124;")


def render_diagram(
    nodes: list[DiagramNode], edges: list[DiagramEdge], *,
    fmt: str, truncated: bool = False,
) -> str:
    if fmt not in {"mermaid", "plantuml"}:
        raise ValueError(f"Unsupported diagram format: {fmt}")

    ordered_nodes = sorted(nodes, key=lambda node: (node.name.casefold(), node.id))
    ids = {node.id for node in ordered_nodes}
    ordered_edges = sorted(
        (edge for edge in edges if edge.from_id in ids and edge.to_id in ids),
        key=lambda edge: (edge.from_id, edge.to_id, edge.relationship_type),
    )
    summary = f"nodes={len(ordered_nodes)} edges={len(ordered_edges)}"
    if truncated:
        summary += " truncated=true"

    if fmt == "mermaid":
        lines = ["flowchart LR", f"  %% {summary}"]
        for node in ordered_nodes:
            lines.append(
                f'  {_alias(node.id)}["{_label(node.name)} ({_label(node.entity_type)})"]'
            )
        for edge in ordered_edges:
            lines.append(
                f"  {_alias(edge.from_id)} -->|{_label(edge.relationship_type)}| "
                f"{_alias(edge.to_id)}"
            )
    else:
        lines = ["@startuml", "left to right direction", f"' {summary}"]
        for node in ordered_nodes:
            lines.append(
                f'rectangle "{_label(node.name)} ({_label(node.entity_type)})" '
                f"as {_alias(node.id)}"
            )
        for edge in ordered_edges:
            lines.append(
                f"{_alias(edge.from_id)} --> {_alias(edge.to_id)} : "
                f"{_label(edge.relationship_type)}"
            )
        lines.append("@enduml")
    return "\n".join(lines) + "\n"
