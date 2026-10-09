"""Graph index and traversal.

The index is an in-memory adjacency structure built from persisted entities and
relationships. It is deliberately independent of SQLAlchemy so it can be
constructed from a fixture, a JSON export or a live database, and so the
algorithms are trivially unit-testable.

Two directions matter:

``influence``
    "If I change A, what breaks?" — follows :data:`atlas.domain.RELATIONSHIP_FLOW`.
``dependency``
    "What does A need in order to work?" — the opposite direction.

Each relationship is stored in English statement order
(``student_export.py READS_FROM Student.Person``) and expands to one or two
*influence arcs* depending on its flow. Arcs, not relationships, are what the
traversal walks.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass, field

from atlas.domain import Flow, RelationshipType, ReviewStatus
from atlas.models import Entity, Relationship


@dataclass(frozen=True)
class Edge:
    """A stored relationship with influence direction resolved."""

    id: str
    source_id: str
    target_id: str
    relationship_type: RelationshipType
    confidence: str
    review_status: str
    label: str = ""

    @property
    def flow(self) -> Flow:
        return self.relationship_type.flow

    @property
    def is_bidirectional(self) -> bool:
        return self.flow is Flow.BOTH

    @property
    def flow_from(self) -> str:
        """Primary display direction start (source->target for FORWARD/BOTH)."""
        if self.flow is Flow.REVERSE:
            return self.target_id
        return self.source_id

    @property
    def flow_to(self) -> str:
        if self.flow is Flow.REVERSE:
            return self.source_id
        return self.target_id

    def arcs(self) -> list[tuple[str, str]]:
        """Directed influence arcs ``(from_id, to_id)`` this edge contributes."""
        if self.flow is Flow.FORWARD:
            return [(self.source_id, self.target_id)]
        if self.flow is Flow.REVERSE:
            return [(self.target_id, self.source_id)]
        return [(self.source_id, self.target_id), (self.target_id, self.source_id)]

    def other_end(self, entity_id: str) -> str:
        return self.target_id if self.source_id == entity_id else self.source_id


@dataclass(frozen=True)
class Arc:
    from_id: str
    to_id: str
    edge: Edge


@dataclass
class Step:
    entity_id: str
    depth: int
    edge: Edge | None = None
    #: Which end of ``edge`` we arrived from, for accurate rendering.
    via_from: str | None = None


@dataclass
class TraversalResult:
    root_id: str
    direction: str
    steps: list[Step]
    truncated: bool = False

    @property
    def entity_ids(self) -> list[str]:
        return [s.entity_id for s in self.steps]

    def includes(self, entity_id: str) -> bool:
        return any(s.entity_id == entity_id for s in self.steps)


@dataclass
class PathResult:
    found: bool
    entity_ids: list[str] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    mode: str = "none"


class GraphIndex:
    """Adjacency index over a workspace's entities and relationships."""

    def __init__(
        self,
        entities: Iterable[Entity],
        relationships: Iterable[Relationship | Edge],
        *,
        include_rejected: bool = False,
    ) -> None:
        self.nodes: dict[str, Entity] = {}
        self.edges: list[Edge] = []
        self._out: dict[str, list[Arc]] = defaultdict(list)
        self._in: dict[str, list[Arc]] = defaultdict(list)
        self._degree: dict[str, int] = defaultdict(int)
        self.include_rejected = include_rejected

        for entity in entities:
            if not getattr(entity, "is_active", True):
                continue
            self.nodes[entity.id] = entity

        for rel in relationships:
            if not getattr(rel, "is_active", True):
                continue
            edge = rel if isinstance(rel, Edge) else edge_from_relationship(rel)
            if not include_rejected and edge.review_status == ReviewStatus.REJECTED.value:
                continue
            if edge.source_id not in self.nodes or edge.target_id not in self.nodes:
                continue
            self.edges.append(edge)
            for from_id, to_id in edge.arcs():
                arc = Arc(from_id=from_id, to_id=to_id, edge=edge)
                self._out[from_id].append(arc)
                self._in[to_id].append(arc)
            self._degree[edge.source_id] += 1
            self._degree[edge.target_id] += 1

    # -- basic accessors ---------------------------------------------------- #
    def has(self, entity_id: str) -> bool:
        return entity_id in self.nodes

    def degree(self, entity_id: str) -> int:
        return self._degree.get(entity_id, 0)

    def neighbours(self, entity_id: str) -> list[str]:
        seen: dict[str, None] = {}
        for arc in self._out.get(entity_id, []) + self._in.get(entity_id, []):
            other = arc.to_id if arc.from_id == entity_id else arc.from_id
            if other != entity_id:
                seen.setdefault(other)
        return list(seen)

    def edges_of(self, entity_id: str) -> list[Edge]:
        seen: dict[str, None] = {}
        for arc in self._out.get(entity_id, []) + self._in.get(entity_id, []):
            seen.setdefault(arc.edge.id)
        return [e for e in self.edges if e.id in seen]

    def incident_edges(self, entity_id: str) -> list[Edge]:
        return [e for e in self.edges if e.source_id == entity_id or e.target_id == entity_id]

    # -- traversal ---------------------------------------------------------- #
    def traverse(
        self,
        root_id: str,
        *,
        direction: str = "downstream",
        max_depth: int | None = None,
        limit: int = 5000,
    ) -> TraversalResult:
        """Breadth-first traversal.

        ``downstream`` follows influence arcs (what this change can affect).
        ``upstream`` follows them in reverse (what this thing depends on).
        ``max_depth=None`` means "everything reachable".
        """
        if root_id not in self.nodes:
            return TraversalResult(root_id=root_id, direction=direction, steps=[])

        adjacency = self._out if direction == "downstream" else self._in
        steps: list[Step] = [Step(entity_id=root_id, depth=0)]
        seen: set[str] = {root_id}
        queue: deque[tuple[str, int]] = deque([(root_id, 0)])
        truncated = False

        while queue:
            current, depth = queue.popleft()
            if max_depth is not None and depth >= max_depth:
                continue
            for arc in adjacency.get(current, []):
                nxt = arc.to_id if direction == "downstream" else arc.from_id
                if nxt in seen:
                    continue
                seen.add(nxt)
                steps.append(
                    Step(entity_id=nxt, depth=depth + 1, edge=arc.edge, via_from=arc.from_id)
                )
                if len(steps) >= limit:
                    truncated = True
                    queue.clear()
                    break
                queue.append((nxt, depth + 1))

        return TraversalResult(
            root_id=root_id, direction=direction, steps=steps, truncated=truncated
        )

    def downstream(self, root_id: str, max_depth: int | None = None) -> TraversalResult:
        return self.traverse(root_id, direction="downstream", max_depth=max_depth)

    def upstream(self, root_id: str, max_depth: int | None = None) -> TraversalResult:
        return self.traverse(root_id, direction="upstream", max_depth=max_depth)

    def direct_neighbourhood(self, root_id: str) -> TraversalResult:
        """Root plus immediate influence neighbours with their connecting edge."""
        if root_id not in self.nodes:
            return TraversalResult(root_id=root_id, direction="both", steps=[])
        steps: list[Step] = [Step(entity_id=root_id, depth=0)]
        seen: set[str] = {root_id}
        for arc in self._out.get(root_id, []) + self._in.get(root_id, []):
            other = arc.to_id if arc.from_id == root_id else arc.from_id
            if other in seen:
                continue
            seen.add(other)
            steps.append(
                Step(entity_id=other, depth=1, edge=arc.edge, via_from=arc.from_id)
            )
        return TraversalResult(root_id=root_id, direction="both", steps=steps)

    # -- path finding ------------------------------------------------------- #
    def find_path(self, from_id: str, to_id: str, *, max_depth: int = 25) -> PathResult:
        """Shortest influence path from ``from_id`` to ``to_id``.

        Falls back to the undirected graph so the user still gets an answer
        when the two entities are connected against the influence direction;
        the returned edges keep their true direction so the UI can say so.
        """
        if from_id not in self.nodes or to_id not in self.nodes:
            return PathResult(found=False)
        if from_id == to_id:
            return PathResult(found=True, entity_ids=[from_id], mode="downstream")

        chain = self._bfs_path(from_id, to_id, "downstream", max_depth)
        mode = "downstream"
        if chain is None:
            chain = self._bfs_path(from_id, to_id, "upstream", max_depth)
            mode = "upstream"
        if chain is None:
            chain = self._bfs_path(from_id, to_id, "undirected", max_depth)
            mode = "connected"
        if chain is None:
            return PathResult(found=False)
        return PathResult(
            found=True, entity_ids=self._chain_entity_ids(from_id, to_id, chain),
            edges=chain, mode=mode,
        )

    def _bfs_path(
        self,
        from_id: str,
        to_id: str,
        mode: str,
        max_depth: int,
    ) -> list[Edge] | None:
        """BFS returning the edge chain, or ``None`` if unreachable."""
        parent: dict[str, tuple[str, Edge] | None] = {from_id: None}
        queue: deque[str] = deque([from_id])
        visited = 0
        budget = max_depth * 400
        while queue and visited < budget:
            visited += 1
            current = queue.popleft()
            if current == to_id:
                break
            for nxt, edge in self._step_edges(current, mode):
                if nxt in parent:
                    continue
                parent[nxt] = (current, edge)
                queue.append(nxt)
        if to_id not in parent:
            return None
        chain: list[Edge] = []
        cursor = to_id
        while parent.get(cursor) is not None:
            prev, edge = parent[cursor]  # type: ignore[misc]
            chain.append(edge)
            cursor = prev
        chain.reverse()
        return chain

    def _step_edges(self, current: str, mode: str) -> list[tuple[str, Edge]]:
        out: list[tuple[str, Edge]] = []
        if mode in {"downstream", "undirected"}:
            for arc in self._out.get(current, []):
                out.append((arc.to_id, arc.edge))
        if mode in {"upstream", "undirected"}:
            for arc in self._in.get(current, []):
                out.append((arc.from_id, arc.edge))
        return out

    def _chain_entity_ids(self, from_id: str, to_id: str, chain: list[Edge]) -> list[str]:
        if not chain:
            return [from_id, to_id]
        ids = [from_id]
        current = from_id
        for edge in chain:
            current = edge.other_end(current)
            ids.append(current)
        return ids

    # -- analytics ---------------------------------------------------------- #
    def dependency_chains(self, root_id: str, *, max_chains: int = 12) -> list[list[Step]]:
        """Representative downstream chains for display.

        Depth-first, preferring high-degree neighbours, so the chains read like
        real end-to-end integration flows rather than arbitrary BFS order.
        """
        if root_id not in self.nodes:
            return []
        chains: list[list[Step]] = []
        seen_edges: set[str] = set()

        def walk(current: str, chain: list[Step], depth: int) -> None:
            if len(chains) >= max_chains or depth > 14:
                return
            arcs = sorted(
                self._out.get(current, []),
                key=lambda a: (-self.degree(a.to_id), a.edge.relationship_type.value, a.to_id),
            )
            progressed = False
            for arc in arcs:
                if arc.edge.id in seen_edges:
                    continue
                seen_edges.add(arc.edge.id)
                progressed = True
                walk(
                    arc.to_id,
                    chain + [Step(entity_id=arc.to_id, depth=depth + 1, edge=arc.edge, via_from=current)],
                    depth + 1,
                )
            if not progressed and len(chain) > 1:
                chains.append(chain)

        walk(root_id, [Step(entity_id=root_id, depth=0)], 0)
        return chains

    def hubs(self, top: int = 10) -> list[tuple[str, int]]:
        ranked = sorted(self._degree.items(), key=lambda kv: (-kv[1], kv[0]))
        return [(eid, deg) for eid, deg in ranked[:top] if deg > 0]


def edge_from_relationship(rel: Relationship) -> Edge:
    return Edge(
        id=rel.id,
        source_id=rel.source_id,
        target_id=rel.target_id,
        relationship_type=RelationshipType(rel.relationship_type),
        confidence=rel.confidence,
        review_status=rel.review_status,
        label=rel.label,
    )
