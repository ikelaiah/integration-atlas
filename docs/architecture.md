# Architecture

Integration Atlas reconstructs an organisation's integration estate from the
artefacts it already has — scripts, SQL, config files, scheduler exports — and
answers impact questions about it.

## The pipeline

```text
Discover  →  Extract  →  Normalise  →  Link  →  Visualise  →  Analyse
   │            │            │           │            │            │
 walk FS    scanners    entities +   fingerprints  React Flow   traversal
            (plugins)   relationships + evidence    + panels     + risk
```

Each stage has one job and one owner module. The important property is that
**discovery is completely independent of the web application**: the CLI and the
API call the same services.

## Layout

```text
integration-atlas/
├── backend/atlas/
│   ├── api/            FastAPI app + route modules + serialisers
│   ├── scanners/       discovery plugins + walker + normaliser + runner
│   ├── services/       graph traversal, impact, search, risk, redaction, export
│   ├── demo/           the Northstar demo estate + seeder
│   ├── models.py       SQLAlchemy ORM
│   ├── schemas.py      Pydantic request/response contracts
│   ├── domain.py       enums and semantics (pure Python, no I/O)
│   ├── db.py           engine/session management
│   ├── config.py       settings
│   └── cli.py          the `atlas` command
├── frontend/src/       React + TypeScript + Tailwind application
├── examples/           realistic artefacts you can point a scan at
├── tests/              pytest suite with real fixtures
└── docs/               this documentation
```

`domain.py` has no dependencies. Everything else imports from it, so the
vocabulary of the product — entity types, relationship types, confidence
levels, flow semantics — is defined exactly once.

## Layering

```text
  cli.py ─┐
          ├──► services/ ──► models.py ──► db.py ──► SQLite
  api/ ───┘        ▲
                   │
              scanners/ (no persistence knowledge)
```

Rules that keep this maintainable:

1. **Scanners never touch the database.** They emit `EntityCandidate`,
   `RelationshipCandidate` and `ScanResult` values. The normaliser decides
   what those become.
2. **Services never know about HTTP.** They take entities and relationships
   and return plain data structures. The API serialises them.
3. **`domain.py` never imports from the rest of the package.** If you find
   yourself adding an import there, the concept belongs somewhere else.
4. **Secret redaction runs at the parser boundary**, before any candidate can
   reach persistence. See `docs/security.md`.

## Persistence

SQLAlchemy 2.0 ORM over SQLite by default. The models are dialect-neutral —
the only SQLite-specific behaviour is three connection pragmas in `db.py`, so
moving to PostgreSQL later is a URL change.

Identifiers are text UUIDs. Rows carry a `fingerprint` column: a natural key
used to reconcile entities and relationships across rescans. Without it, a
rescan would duplicate everything.

## Graph model

Relationships are stored in **English statement order**:

```text
export_students.ps1  --READS_FROM-->  LegacySIS.Student.Person
```

but influence propagates in a direction declared per relationship type
(`Flow.FORWARD`, `Flow.REVERSE`, `Flow.BOTH`). Impact analysis walks the
influence direction; "what does this depend on?" walks the opposite one.

This is the least surprising model: the stored statement reads correctly in
prose, the arrows on the map read correctly as a data-flow diagram, and the
traversal is correct rather than approximate. See
`docs/adr/002-relationship-flow-semantics.md`.

Graph algorithms run **server-side** over an in-memory adjacency index
(`services/graph.py`). The index is constructed from ORM rows or from any
other source, which makes the algorithms trivially unit-testable.

## Discovery

```python
class Scanner(Protocol):
    name: str
    extensions: frozenset[str]
    def can_scan(self, path: Path) -> bool: ...
    def scan(self, path: Path, text: str) -> ScanResult: ...
```

Four plugins ship today: Python, PowerShell, SQL, and config/scheduler
(JSON, YAML, XML, INI, `.env`, Windows Task Scheduler, cron). Adding a
language means adding one class.

Scanners are **static by design** — no code is executed, no environment is
simulated. They match the patterns that carry integration knowledge: SQL in
strings, HTTP calls, file IO, connection strings, UNC paths, scheduler
entries. Every observation carries the file, line and a redacted snippet so
the user can see exactly why Atlas believes something.

## Frontend

React + TypeScript + Vite + Tailwind. The atlas canvas is
[React Flow](https://reactflow.dev) with custom nodes; layout is a hand-rolled
Sugiyama-style layered algorithm (`lib/layout.ts`) tuned for integration
graphs — few wide layers, long chains, node sizes that vary by entity type.

State is local to the page that owns it. There is no global store; the graph
data is fetched once per workspace/filter combination and derived views
(highlight sets, filters, search) are computed with `useMemo`. That is
deliberately boring and scales to the 10k-entity target without ceremony.

The API client is a thin typed wrapper over `fetch` (`lib/api.ts`). The types
mirror the Pydantic schemas one-for-one.

## Performance envelope

Designed and tested for **10,000 entities / 50,000 relationships**.

* Graph payloads are capped (`max_graph_nodes`, default 2000) and filtered
  server-side before they reach the browser.
* Traversal is BFS over adjacency lists — O(V + E).
* Search scores every entity in memory. At 10k entities that is
  imperceptible, and it keeps ranking identical across database backends.
* The graph renderer only mounts nodes that survive the active filters.

## What is deliberately not here

No microservices, no message bus, no cache layer, no ORM abstraction over the
abstraction, no LLM calls, no telemetry. If a future requirement needs one of
those, it should arrive with a written reason in `docs/adr/`.
