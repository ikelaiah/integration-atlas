# Integration Atlas — Task Checklist

## Phase A — Foundations
- [x] A1. Repo scaffold (pyproject, layout, gitignore, LICENSE)
- [x] A2. Architecture + domain model docs + ADRs
- [x] A3. Enums, SQLAlchemy models, Pydantic schemas
- [x] A4. DB session + repositories
- [x] A5. Secret redaction + tests

## Phase B — Domain services
- [x] B1. Graph traversal (upstream/downstream)
- [x] B2. Impact analysis
- [x] B3. Path finder
- [x] B4. Search
- [x] B5. Risk engine

## Phase C — Demo dataset
- [x] C1. Northstar demo fixture
- [x] C2. Seeder

## Phase D — API
- [x] D1. FastAPI routes (entities, relationships, graph, search, impact, path)
- [x] D2. Workspace + scan routes + OpenAPI
- [x] D3. API tests

## Phase E — Frontend
- [x] E1. App shell + design system
- [x] E2. Atlas graph (React Flow, custom nodes, filters, hover)
- [x] E3. Entity detail panel
- [x] E4. Impact mode + path explorer
- [x] E5. Dashboard + search + command palette
- [x] E6. Polish pass

## Phase F — Discovery engine
- [x] F1. Scanner plugin base + walker
- [x] F2. Redaction in pipeline
- [x] F3. Python scanner
- [x] F4. PowerShell scanner
- [x] F5. SQL scanner
- [x] F6. Config/scheduler scanner
- [x] F7. Normaliser
- [x] F8. Scanner tests

## Phase G — Hardening
- [x] G1. README
- [x] G2. Security doc
- [x] G3. Export + CLI
- [x] G4. Full verification
- [x] G5. Acceptance test for the first vertical slice
- [x] G6. Optional Docker convenience (Dockerfile + compose)
- [x] G7. ruff clean across backend + tests

## v0.2.0 — Trust and Review

- [x] Scan preview with durable rollback, shared path validation and bounded diff
- [x] Applied scan history with actual diff and consistent API response
- [x] Review queue API with evidence, verdict and redacted note
- [x] Scan preview/apply and review queue UI
- [x] Entity edit form and refreshed graph/detail state
- [x] Operator docs, release notes and version 0.2.0
- [ ] Backend and frontend checks, code review, CI, release and Pages verification
