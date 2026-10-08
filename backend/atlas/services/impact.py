"""Impact analysis.

Turns a graph traversal into the answer to "if I change this, what breaks?" —
grouped counts, an explicit list of affected artefacts and a handful of
representative dependency chains so the result is readable, not just a number.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from atlas.domain import EntityType
from atlas.services.graph import Edge, GraphIndex, Step


@dataclass
class ImpactItem:
    entity_id: str
    depth: int
    via: Edge | None = None


@dataclass
class ImpactResult:
    root_id: str
    direction: str
    max_depth: int | None
    items: list[ImpactItem] = field(default_factory=list)
    chains: list[list[Step]] = field(default_factory=list)
    truncated: bool = False

    @property
    def total(self) -> int:
        return len(self.items)

    def counts_by_type(self, index: GraphIndex) -> Counter[str]:
        counter: Counter[str] = Counter()
        for item in self.items:
            node = index.nodes.get(item.entity_id)
            if node is not None:
                counter[node.entity_type] += 1
        return counter


# Roll-up buckets used by the impact headline. They overlap on purpose: an
# integration is also often a script, and we want both numbers.
_ROLLUP: dict[str, tuple[EntityType, ...]] = {
    "integrations": (EntityType.INTEGRATION, EntityType.SYSTEM, EntityType.APPLICATION),
    "scripts": (EntityType.SCRIPT,),
    "jobs": (EntityType.SCHEDULED_JOB,),
    "files": (EntityType.FILE, EntityType.DIRECTORY, EntityType.SFTP_LOCATION),
    "external_services": (EntityType.EXTERNAL_SERVICE, EntityType.API, EntityType.ENDPOINT),
    "databases": (EntityType.DATABASE, EntityType.SCHEMA, EntityType.TABLE, EntityType.COLUMN),
}


def analyse_impact(
    index: GraphIndex,
    entity_id: str,
    *,
    direction: str = "downstream",
    max_depth: int | None = None,
    include_root: bool = False,
    max_items: int = 2000,
) -> ImpactResult:
    traversal = index.traverse(entity_id, direction=direction, max_depth=max_depth)

    items: list[ImpactItem] = []
    for step in traversal.steps:
        if step.depth == 0 and not include_root:
            continue
        items.append(ImpactItem(entity_id=step.entity_id, depth=step.depth, via=step.edge))

    result = ImpactResult(
        root_id=entity_id,
        direction=direction,
        max_depth=max_depth,
        items=items[:max_items],
        truncated=traversal.truncated or len(items) > max_items,
    )
    if direction == "downstream":
        result.chains = index.dependency_chains(entity_id, max_chains=10)
    return result


def rollup_counts(index: GraphIndex, result: ImpactResult) -> dict[str, int]:
    counts = result.counts_by_type(index)
    out: dict[str, int] = {}
    matched: set[EntityType] = set()
    for bucket, types in _ROLLUP.items():
        total = sum(counts.get(t.value, 0) for t in types)
        out[bucket] = total
        matched.update(types)
    out["other"] = sum(v for k, v in counts.items() if EntityType(k) not in matched)
    return out


def impact_to_dict(index: GraphIndex, result: ImpactResult) -> dict:
    from atlas.api.serialisers import node_dict

    counts = result.counts_by_type(index)
    groups = []
    for etype, count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        entities = [
            node_dict(index.nodes[item.entity_id])
            for item in result.items
            if index.nodes.get(item.entity_id) is not None
            and index.nodes[item.entity_id].entity_type == etype
        ]
        groups.append(
            {
                "entity_type": etype,
                "label": EntityType(etype).label,
                "count": count,
                "entities": entities[:50],
            }
        )
    rollup = rollup_counts(index, result)
    return {
        "root": node_dict(index.nodes[result.root_id]),
        "direction": result.direction,
        "max_depth": result.max_depth,
        "total_affected": result.total,
        "groups": groups,
        "chains": [
            [
                {
                    "entity": node_dict(index.nodes[s.entity_id]),
                    "depth": s.depth,
                    "relationship": _edge_dict(s.edge) if s.edge else None,
                }
                for s in chain
                if s.entity_id in index.nodes
            ]
            for chain in result.chains
        ],
        "truncated": result.truncated,
        **rollup,
    }


def _edge_dict(edge: Edge | None) -> dict | None:
    if edge is None:
        return None
    return {
        "id": edge.id,
        "source_id": edge.source_id,
        "target_id": edge.target_id,
        "relationship_type": edge.relationship_type.value,
        "flow_from": edge.flow_from,
        "flow_to": edge.flow_to,
        "confidence": edge.confidence,
        "review_status": edge.review_status,
        "label": edge.label,
    }
