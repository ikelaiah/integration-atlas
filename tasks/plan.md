# Implementation Plan: Integration Atlas

## Overview

Integration Atlas is a local-first discovery and visualisation tool that reconstructs an
organisation's integration estate from the artefacts it already has (scripts, SQL, config,
scheduler exports, file drops), then answers impact questions: *"if I change this table,
what breaks?"*

This plan covers Phase 1 (the shippable MVP) with the **first vertical slice** as the
primary milestone: load the Northstar demo, explore a beautiful dependency graph, select
`LegacySIS.Student.StudentID`, run impact analysis, and see every downstream dependency
highlighted.

## Architecture Decisions

| # | Decision | Rationale |
|---|---|---|
| A1 | Monorepo: `backend/atlas` installable package + `frontend` Vite app | Single clone, `pip install -e .` gives `atlas` CLI and API; frontend is a separate build step |
| A2 | SQLite default via SQLAlchemy 2.0 ORM; dialect-neutral models | Zero-setup local-first; PostgreSQL later needs only a URL change |
| A3 | Sync SQLAlchemy + FastAPI (no async ORM) | 10k entities is trivial for SQLite; async adds complexity with no payoff |
| A4 | Relationships stored as `source --type--> target` with a **flow map** per type | Preserves natural English statements (`script READS_FROM table`) while enabling correct impact traversal (see ADR-002) |
| A5 | Evidence is first-class and attached to entities *and* relationships | Every inferred edge must be explainable; this is the product's differentiator |
| A6 | Secret redaction happens at the parser boundary, before persistence | Nothing sensitive ever reaches the DB or logs (ADR-004) |
| A7 | React Flow for the atlas graph | Best-in-class interactive node graphs (zoom/pan/drag/custom nodes) with React ergonomics |
| A8 | Graph algorithms run server-side (BFS over adjacency), client renders results | Single source of truth; API is reusable by CLI and future exports |
| A9 | Demo dataset is code (`backend/atlas/demo/northstar.py`), seeded on demand | Versionable, testable, no binary fixtures |
| A10 | Scanners are a plugin registry (`Scanner.can_scan` / `Scanner.scan`) | Discovery logic is independent of the web app and extensible |

## Domain Model (summary)

See `docs/domain-model.md` for the full reference.

```
Workspace 1──* Entity 1──* Evidence
                 │ 1
                 │
                 * Relationship *──1 Entity
                    │ 1
                    * Evidence

Workspace 1──* Scan 1──* ScanEvent
Workspace 1──* RiskFinding
```

**Entity types:** System, Application, Server, Database, Schema, Table, Column, Script,
ScheduledJob, Api, Endpoint, File, Directory, SftpLocation, Queue, ExternalService,
Integration.

**Relationship types:** READS_FROM, WRITES_TO, CALLS, RUNS, RUNS_ON, DEPENDS_ON,
PRODUCES, CONSUMES, TRANSFERS_TO, IMPORTS_FROM, EXPORTS_TO, TRIGGERS, USES_TABLE,
USES_COLUMN, CONNECTS_TO.

**Confidence:** Confirmed > High > Medium > Low, plus Manual. Every relationship carries
confidence + evidence; users can confirm/reject.

**Flow semantics:** each relationship type maps to `FORWARD` (influence flows
source→target) or `REVERSE`. Impact analysis follows FORWARD edges; dependency discovery
follows REVERSE edges. See ADR-002.

## Task List

### Phase A — Foundations

- [x] A1. Repo scaffold: `pyproject.toml`, package layout, `.gitignore`, LICENSE
- [x] A2. Architecture + domain model docs, ADR-001..004
- [x] A3. Enums + SQLAlchemy ORM models + Pydantic schemas
- [x] A4. Database session management + repository layer
- [x] A5. Secret redaction service + tests

### Checkpoint A: `python -c "import atlas"` works, tests for redaction pass

### Phase B — Domain services

- [x] B1. Graph service: adjacency build, upstream/downstream traversal
- [x] B2. Impact analysis service (depth, direction, categorised counts)
- [x] B3. Path finder (BFS shortest influence path with labelled steps)
- [x] B4. Search service (token + fuzzy scoring across entity fields)
- [x] B5. Risk engine (explainable heuristics)

### Checkpoint B: service-level tests pass against an in-memory graph

### Phase C — Demo dataset

- [x] C1. Northstar Education Group fixture (~18 systems, 30+ integrations, 60+ nodes)
- [x] C2. Seeder that persists demo into a workspace

### Checkpoint C: `atlas demo` seeds a queryable workspace

### Phase D — API

- [x] D1. FastAPI app + typed routes: entities, relationships, graph, search, impact, path
- [x] D2. Workspace + scan routes; OpenAPI metadata
- [x] D3. API tests

### Checkpoint D: `atlas serve` serves OpenAPI + JSON

### Phase E — Frontend vertical slice

- [x] E1. Vite + React + TS + Tailwind + shadcn-style primitives, app shell + sidebar
- [x] E2. Atlas graph page: React Flow, custom nodes, legend, filters, hover dimming
- [x] E3. Entity detail panel with Overview / Dependencies / Evidence / Risks tabs
- [x] E4. Impact analysis mode + dependency path explorer
- [x] E5. Overview dashboard + global search + command palette (Ctrl+K)
- [x] E6. Dark-first visual polish pass, empty/loading states

### Checkpoint E: first vertical slice demoable end-to-end

### Phase F — Discovery engine

- [x] F1. Scanner plugin base + file walker + text extraction
- [x] F2. Secret redaction integrated into the scanner pipeline
- [x] F3. Python scanner (SQL strings, HTTP, file IO, subprocess, DB drivers, env vars)
- [x] F4. PowerShell scanner (Invoke-*, Sqlcmd, file IO, UNC paths, URLs)
- [x] F5. SQL scanner (tables/schemas/columns/DML/EXEC; SQL Server + generic)
- [x] F6. Config scanner (JSON/YAML/XML/INI/.env) + scheduler XML + cron
- [x] F7. Normaliser: scanner findings → entities + relationships + evidence
- [x] F8. Scanner tests with realistic fixtures + secret-leakage tests

### Checkpoint F: `atlas scan ./examples` discovers entities end-to-end

### Phase G — Hardening & docs

- [x] G1. README (problem, features, quick start, architecture, security, roadmap)
- [x] G2. Security model doc
- [x] G3. Export (JSON / CSV / GraphML) + CLI polish
- [x] G4. Full test run + type/lint pass

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Graph becomes spaghetti with 50+ nodes | High | Node-type filters, focus mode, progressive neighbour expansion, edge bundling by default |
| Frontend polish time dwarfs logic | High | Build the shell + graph first; visual quality gate applied per surface |
| Scanner false positives erode trust | High | Confidence scoring + evidence for every edge; users can confirm/reject |
| Secret leakage in fixtures/tests | High | Redaction applied at parse time; dedicated leak tests assert no secret substring in DB |
| Scope creep beyond Phase 1 | Medium | Task list is the contract; Phase 2/3 items recorded but not built |

## Open Questions

- None blocking. Phase 2 items (rescan reconciliation, manual editing UI, Windows
  Scheduler XML, cron, GraphML export, risk UI) are deferred by design.

## v0.2.0 — Trust and Review

See [the v0.2.0 specification](v0.2.0-spec.md). Ship in four vertical slices:

1. Make scan history use the documented progress response; compute bounded graph
   diffs for applied scans and rollback preview scans. Verify with API tests.
2. Add a relationship review queue, evidence display, verdicts and notes. Verify
   filtering, redaction and verdict survival after rescanning.
3. Add entity editing in the detail panel and the scan preview/apply UI. Verify
   manual field survival, frontend type checking and production build.
4. Update operator docs and version metadata; run full checks, review the diff,
   merge after CI, publish v0.2.0 and verify GitHub Pages deployment.
