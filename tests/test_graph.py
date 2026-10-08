"""Tests for graph traversal, impact analysis and path finding.

Built on a small in-memory fixture that mirrors the Northstar student-export
story so the semantics stay honest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from atlas.domain import EntityType, Flow, RelationshipType
from atlas.services.graph import Edge, GraphIndex
from atlas.services.impact import analyse_impact, rollup_counts


@dataclass
class FakeEntity:
    id: str
    name: str
    entity_type: str
    qualified_name: str = ""
    technology: str = ""
    environment: str = "production"
    owner: str = ""
    risk_level: str | None = None
    confidence: str = "high"
    is_missing: bool = False
    meta_json: dict[str, Any] = field(default_factory=dict)
    workspace_id: str = "w1"


def make_edge(src: str, dst: str, rel: RelationshipType, eid: str | None = None) -> Edge:
    return Edge(
        id=eid or f"{src}:{rel.value}:{dst}",
        source_id=src,
        target_id=dst,
        relationship_type=rel,
        confidence="high",
        review_status="proposed",
        label="",
    )


@pytest.fixture()
def student_index() -> GraphIndex:
    entities = [
        FakeEntity("col", "StudentID", "column", "LegacySIS.Student.Person.StudentID"),
        FakeEntity("table", "Person", "table", "LegacySIS.Student.Person"),
        FakeEntity("sql", "student_extract.sql", "script"),
        FakeEntity("ps1", "export_students.ps1", "script"),
        FakeEntity("csv", "students.csv", "file"),
        FakeEntity("job", "nightly-student-export", "scheduled_job"),
        FakeEntity("ident", "identity_sync.py", "script"),
        FakeEntity("api", "IdentityHub SCIM API", "api"),
        FakeEntity("sys", "IdentityHub", "system"),
    ]
    edges = [
        make_edge("sql", "table", RelationshipType.READS_FROM),
        make_edge("sql", "col", RelationshipType.USES_COLUMN),
        make_edge("ps1", "sql", RelationshipType.RUNS),
        make_edge("job", "ps1", RelationshipType.RUNS),
        make_edge("ps1", "csv", RelationshipType.PRODUCES),
        make_edge("ident", "csv", RelationshipType.CONSUMES),
        make_edge("ident", "sys", RelationshipType.CALLS),
        make_edge("api", "sys", RelationshipType.DEPENDS_ON),
    ]
    return GraphIndex(entities, edges)  # type: ignore[arg-type]


def test_flow_semantics_table() -> None:
    assert RelationshipType.READS_FROM.flow is Flow.REVERSE
    assert RelationshipType.PRODUCES.flow is Flow.FORWARD
    assert RelationshipType.CALLS.flow is Flow.BOTH
    assert RelationshipType.USES_COLUMN.flow is Flow.REVERSE


def test_downstream_from_column_reaches_external_system(student_index: GraphIndex) -> None:
    result = student_index.downstream("col")
    reached = set(result.entity_ids)
    assert reached == {"col", "sql", "ps1", "job", "csv", "ident", "api", "sys"}


def test_downstream_respects_max_depth(student_index: GraphIndex) -> None:
    result = student_index.downstream("col", max_depth=1)
    assert set(result.entity_ids) == {"col", "sql"}


def test_upstream_from_csv_returns_its_dependencies(student_index: GraphIndex) -> None:
    result = student_index.upstream("csv")
    reached = set(result.entity_ids)
    assert "ps1" in reached
    assert "sql" in reached
    assert "table" in reached
    assert "ident" not in reached


def test_calls_edges_propagate_both_ways() -> None:
    entities = [FakeEntity("a", "a", "script"), FakeEntity("b", "b", "api")]
    edges = [make_edge("a", "b", RelationshipType.CALLS)]
    index = GraphIndex(entities, edges)  # type: ignore[arg-type]
    assert "b" in index.downstream("a").entity_ids
    assert "a" in index.downstream("b").entity_ids
    assert "b" in index.upstream("a").entity_ids


def test_rejected_relationships_are_excluded_by_default() -> None:
    entities = [FakeEntity("a", "a", "script"), FakeEntity("b", "b", "file")]
    edge = make_edge("a", "b", RelationshipType.PRODUCES)
    edge = Edge(
        id=edge.id,
        source_id=edge.source_id,
        target_id=edge.target_id,
        relationship_type=edge.relationship_type,
        confidence=edge.confidence,
        review_status="rejected",
        label="",
    )
    index = GraphIndex(entities, [edge])  # type: ignore[arg-type]
    assert index.downstream("a").entity_ids == ["a"]
    assert GraphIndex(entities, [edge], include_rejected=True).downstream("a").includes("b")


def test_impact_groups_counts(student_index: GraphIndex) -> None:
    result = analyse_impact(student_index, "col")
    counts = result.counts_by_type(student_index)
    assert counts["script"] == 3  # student_extract.sql, export_students.ps1, identity_sync.py
    assert counts["file"] == 1
    assert counts["scheduled_job"] == 1
    assert "col" not in {i.entity_id for i in result.items}

    rollup = rollup_counts(student_index, result)
    assert rollup["scripts"] == 3
    assert rollup["jobs"] == 1
    assert rollup["files"] == 1


def test_impact_chains_are_produced(student_index: GraphIndex) -> None:
    result = analyse_impact(student_index, "col")
    assert result.chains, "expected at least one representative chain"
    flat = {s.entity_id for chain in result.chains for s in chain}
    assert "col" in flat


def test_path_from_table_to_system(student_index: GraphIndex) -> None:
    path = student_index.find_path("table", "sys")
    assert path.found
    assert path.entity_ids[0] == "table"
    assert path.entity_ids[-1] == "sys"
    assert len(path.entity_ids) == len(set(path.entity_ids)), "path should not loop"


def test_path_falls_back_to_undirected(student_index: GraphIndex) -> None:
    # sys -> table is against influence direction, so only the undirected
    # fallback can answer it.
    path = student_index.find_path("sys", "table")
    assert path.found
    assert path.entity_ids[0] == "sys"
    assert path.entity_ids[-1] == "table"


def test_path_not_found(student_index: GraphIndex) -> None:
    lone = FakeEntity("lone", "lonely", "file")
    index = GraphIndex([*student_index.nodes.values(), lone], student_index.edges)  # type: ignore[arg-type]
    assert not index.find_path("col", "lone").found


def test_degree_and_neighbours(student_index: GraphIndex) -> None:
    assert student_index.degree("csv") == 2
    assert set(student_index.neighbours("csv")) == {"ps1", "ident"}


def test_hubs_rank_by_degree(student_index: GraphIndex) -> None:
    hubs = student_index.hubs(top=3)
    assert hubs[0][1] >= hubs[-1][1]
    assert all(deg > 0 for _, deg in hubs)


def test_entity_types_are_well_formed() -> None:
    assert EntityType("script").label == "Script"
    assert RelationshipType("reads_from").label == "Reads from"
