# Integration Atlas roadmap

Make the estate understandable, the answer trustworthy, and the project a
pleasure to work on. A beautiful diagram should help someone explain a real
dependency in a minute, with evidence ready when they ask, “How do you know?”

This plan follows a repository review on **11 October 2026**, at `e22fbbc`
(v0.4.0). Versions below are proposed milestones, not release dates. Each
release has one theme and a few independently reviewable slices.

## What is worth preserving

Atlas already has the right foundations: local static analysis, first-class
evidence, explicit influence semantics, a realistic Northstar story, manual
knowledge that survives rescans, and shared CLI/API services. Scan preview,
relationship review, filtered text diagrams, and historical comparison are
already shipped; this roadmap improves them rather than relisting them.

Keep SQLite and the current React/FastAPI stack. Prefer simpler code and better
defaults before adding infrastructure or more scanners.

## Turn the vision into a quality bar

| Goal | Observable result |
| --- | --- |
| Pleasant to read | The README gets a newcomer to a working demo quickly; deeper explanations have clear entry points and accurate examples. |
| Pleasant to use | Navigation, refresh, back/forward, failures, and workspace changes behave predictably. No failed request masquerades as an empty estate. |
| Pleasant to learn from | A newcomer can trace StudentID to a consumer, explain arrow direction and confidence, and inspect the supporting evidence. |
| Pleasant to maintain | A contributor can follow one fixture through scanner, normaliser, persistence, service, API, and UI; contracts and focused tests catch drift. |
| Wonderful diagrams and results | A focused flow has readable names and arrows, visible limits, and a shareable explanation with provenance. Colour and animation support the story. |

## Review findings that drive the order

“Confirmed” below means reproduced with an isolated Python/API probe.
“Code review” means the behavior or limitation is visible in source; browser
reproduction remains part of the implementation work.

| ID | Priority / evidence | Finding and consequence | Main source | Release |
| --- | --- | --- | --- | --- |
| R1 | Critical / confirmed | The SPA fallback joins a request path to `static_dir` without checking containment. With a built frontend, an encoded parent path returned a harmless marker file outside that directory. Loopback binding limits exposure but does not make the file boundary correct. | [Frontend serving](backend/atlas/api/app.py), `_mount_frontend` | v0.4.1 |
| R2 | High / confirmed | A failing scan returns HTTP 500, but its failed `Scan` row is rolled back by `get_db`. An injected discovery exception left zero scan-history rows, so operators lose the failure record. | [Scan routes](backend/atlas/api/routes/scans.py), [transactions](backend/atlas/db.py) | v0.4.1 |
| R3 | Medium / confirmed | Path search treats `max_depth` as a visit budget, not a hop limit. A 30-hop chain was returned with `max_depth=25`; budget exhaustion is also indistinguishable from no connection. | [Graph service](backend/atlas/services/graph.py), `_bfs_path` | v0.4.1 |
| R4 | High / confirmed export; code review UI | Diagram arrows use influence direction while text exports retain the stored verb: `table → script` is labelled `reads_from`. The canvas uses abbreviated verbs, and both canvas and exports draw only one arrow for bidirectional `CALLS` influence. | [Diagram service](backend/atlas/services/diagrams.py), [graph canvas](frontend/src/components/graph/AtlasGraph.tsx), [domain](backend/atlas/domain.py) | v0.4.2 |
| R5 | High / confirmed API; code review UI | Impact groups silently list at most 50 entities per type. A 60-script result reported 60 affected, listed 50, and said `truncated=false`. Entity inventories also discard the graph response's cap/totals. These views need explicit completeness contracts. | [Impact service](backend/atlas/services/impact.py), [entity inventory](frontend/src/features/entities/EntityListPage.tsx) | v0.4.2 |
| R6 | High / code review | Cross-page actions dispatch transient custom events immediately after navigation; Atlas may not yet have mounted its listeners. Impact requests have no stale-response guard, and workspace changes do not reset all selected entities, panels, or scan previews. | [App](frontend/src/App.tsx), [Atlas page](frontend/src/features/atlas/AtlasPage.tsx), [Scans page](frontend/src/features/scans/ScansPage.tsx) | v0.5.0 |
| R7 | High / code review | Bootstrap, overview, inventories, and risks swallow errors as missing/empty data. A bootstrap failure can leave pages loading indefinitely. Impact failures simply remove the result panel. | [App](frontend/src/App.tsx), [overview](frontend/src/features/overview/OverviewPage.tsx), [impact panel](frontend/src/components/panels/ImpactPanel.tsx) | v0.5.0 |
| R8 | Medium / code review | First launch automatically seeds the demo; the UI can select workspaces but cannot create a real one. Learning and real scanning need an explicit transition. The Settings CLI example omits `scan run`, and the README “Screenshots” section contains descriptions rather than screenshots. | [App](frontend/src/App.tsx), [Settings](frontend/src/features/settings/SettingsPage.tsx), [README](README.md) | v0.5.1 |
| R9 | Medium / code review | The canvas lays out the entire filtered graph; impact dims unrelated nodes rather than creating a focused flow. Layout repeatedly scans edges while sorting, and fixed node/label sizes need visual validation for cycles, long names, and dense branches. | [Layout](frontend/src/lib/layout.ts), [Atlas page](frontend/src/features/atlas/AtlasPage.tsx), [node component](frontend/src/components/graph/EntityNode.tsx) | v0.6.0 |
| R10 | Medium / code review | Mermaid/PlantUML sharing contains names, types, and verbs, but no confidence/evidence context. There is no rendered image export or explicit impact/path export; the current export intentionally excludes path overlays. | [Sharing guide](docs/navigation-and-sharing.md), [exporters](backend/atlas/services/exporters.py) | v0.6.1 |
| R11 | Medium / code review | Frontend types and flow vocabulary are maintained separately from Python contracts; CI checks types/build but has no browser interaction suite. Impact serialization imports an API helper despite the documented service boundary. Historical task notes contain stale deferred features. | [Frontend contracts](frontend/src/lib/types.ts), [architecture](docs/architecture.md), [CI](.github/workflows/ci.yml), [historical plan](tasks/plan.md) | v0.5.0, v0.7.0 |
| R12 | Medium / code review | Architecture docs say the 10,000-entity / 50,000-relationship envelope is tested, but no corresponding benchmark fixture was found. API graph loading builds the full index before filtering; layout and graph edge styling contain repeated full scans. Checkpoints store full before/after graph state without a retention workflow. | [Graph routes](backend/atlas/api/routes/graph.py), [layout](frontend/src/lib/layout.ts), [history](backend/atlas/services/history.py), [architecture](docs/architecture.md) | v0.7.1 |

## Release sequence

| Release | Theme | User-visible outcome | Depends on |
| --- | --- | --- | --- |
| **v0.4.1** | Safe, trustworthy operations | Serving stays inside its directory; failed scans remain explainable; path limits mean what they say. | v0.4.0 |
| **v0.4.2** | Honest diagrams and counts | Arrows read correctly and partial results identify what is missing. | v0.4.1 |
| **v0.5.0** | Reliable user journeys | A click reaches the intended result; refresh, errors, and workspace changes preserve trust. | v0.4.2 |
| **v0.5.1** | A welcoming first ten minutes | New users learn the demo and start a separate real workspace without guesswork. | v0.5.0 |
| **v0.6.0** | Diagrams that tell a story | Focused flows remain legible, navigable, and meaningful without relying on hover. | v0.4.2, v0.5.0 |
| **v0.6.1** | Answers worth sharing | A developer exports a clear diagram and its evidence-backed explanation. | v0.6.0 |
| **v0.7.0** | A project others can understand | Contributors learn one complete feature path and change it with reliable contracts. | v0.6.1 |
| **v0.7.1** | Measured scale and durable history | Large estates expose complete inventories, bounded views, and manageable history. | v0.7.0 |

### v0.4.1 — Safe, trustworthy operations

- [ ] **1A. Contain static file serving (R1).** Resolve the frontend root and
  requested file before serving; reject escapes, including encoded separators,
  absolute paths, and symlinks/junctions where supported. Keep valid assets and
  SPA routes working. Acceptance: an outside marker is never returned.
  Likely files: `api/app.py` and a focused static-serving test module.
- [ ] **1B. Preserve failed scan history (R2).** Roll back discoveries on a
  fatal failure, then save a failed scan record with a redacted, actionable
  error in a separate transaction. Acceptance: history shows the failed attempt
  after a fresh session, with no partial graph changes or successful checkpoint.
  Likely files: `api/routes/scans.py`, the scan orchestration boundary, and tests.
- [ ] **1C. Make path bounds explicit (R3).** Enforce actual BFS hop depth and
  keep any visit budget separate. Distinguish “no path within this depth” from
  exhausted search. Acceptance: boundary, over-depth, cycle, and budget cases
  have deterministic outcomes; the API communicates the limit.
  Likely files: `services/graph.py`, graph schemas/routes, and graph tests.

**Verification:** reproduce R1–R3 as regression tests, run the full backend
suite and lint, and smoke-test built assets plus a deep SPA URL. Ship this
patch before diagram polish.

### v0.4.2 — Honest diagrams and counts

- [ ] **2A. Align arrows with language (R4).** Define display semantics beside
  the canonical domain flow map and expose them to the canvas and text exports.
  Acceptance: `Student.Person → export_students.ps1` says “read by”; a `CALLS`
  relationship shows bidirectional influence while its stored statement remains
  available. Exercise every relationship type. Likely files: domain, graph
  contracts/serializers, diagram service, and graph renderer; split producer
  and consumer changes into small PRs.
- [ ] **2B. Disclose partial results (R5).** Return total, returned, and omitted
  counts for impact groups and capped inventories. Acceptance: 60 affected
  scripts cannot appear as a complete 50-row list; the user sees the limit and
  a clear next step. Keep the deeper pagination work in v0.7.1.
  Likely files: impact service/schema, impact panel, and entity inventory.
- [ ] **2C. Reconcile analysis with the visible graph (R5, R9).** Keep impact
  scope explicit when filters or graph caps hide affected entities. Fetch the
  bounded analysis subgraph needed for highlighting rather than silently using
  only the visible/group-preview entities. Acceptance: the StudentID search can
  lead to a meaningful downstream map, with displayed/affected counts and any
  omitted nodes stated. Likely files: graph/impact routes and Atlas view logic.

**Verification:** semantic export assertions, API completeness tests, and
browser checks for filtered StudentID impact and bidirectional calls. Preserve
redaction, escaping, review exclusions, and deterministic output.

### v0.5.0 — Reliable user journeys

- [ ] **3A. Make navigation durable (R6).** Replace cross-page custom events
  with route/query state for workspace, selected entity, action, and path
  endpoints. Acceptance: selection from overview, inventory, risks, and search
  opens the intended entity; refresh and back/forward restore the view, and
  invalid IDs produce a helpful message. Likely files: App, Atlas, and a small
  navigation helper; add browser regressions for these entry points.
- [ ] **3B. Make requests belong to their workspace (R6).** Clear or revalidate
  panels and scan previews on workspace change; cancel or ignore outdated graph,
  detail, impact, overview, and scan responses. Extract focused hooks only where
  they clarify ownership. Acceptance: delayed responses from workspace A never
  overwrite B, and switching impact direction cannot show the older result.
  Land this page by page, with a focused test for each changed flow.
- [ ] **3C. Make failures useful (R7, R11).** Give bootstrap and each data page
  explicit loading, success, empty, and error states with recovery actions.
  Acceptance: a disconnected API shows a retry action, a zero-result filter
  offers reset, and an impact failure explains what failed. Add a minimal
  browser smoke suite to CI for navigation, failure/retry, and workspace changes.
  Likely files: App, API error handling, affected pages, and CI; split by surface.

**Verification:** real browser tests with delayed/failed requests, direct URLs,
keyboard navigation, and repeated workspace switches; full backend/frontend
checks. Avoid a new global state framework unless these flows require one.

### v0.5.1 — A welcoming first ten minutes

- [ ] **4A. Offer a deliberate starting point (R8).** Present “Explore Northstar”
  and “Create a workspace” on first launch. Add real-workspace creation using
  the existing API, preserve the active choice, and clearly distinguish demo
  reset from real data. Acceptance: a newcomer previews and applies a scan in
  a separate workspace, without mixing it into Northstar.
  Likely files: App, API client, Settings/onboarding, and browser tests.
- [ ] **4B. Teach the first useful question.** Add a short, dismissible Northstar
  path: find StudentID → inspect a relationship → run impact → inspect evidence.
  Explain static-analysis limits, proposed/confirmed discoveries, influence
  arrows, and whole-workspace analysis in context. Acceptance: a first-time
  reader can explain why the CSV junction matters and which claim is inferred.
  Likely files: overview/onboarding, relevant panels, and walkthrough docs.
- [ ] **4C. Make the public introduction match the product (R8, R11).** Tighten
  the README around outcome, installation, and one worked example; link deeper
  CLI/architecture material. Fix stale commands and deferred-feature notes,
  link this roadmap, and replace screenshot placeholders with real, readable
  captures of the released app. Acceptance: documented commands work from a
  clean checkout on Windows and one Unix platform; screenshots match the flow.
  Likely files: README, walkthrough, Settings, and historical task notes.

**Verification:** clean-install smoke checks, isolated demo/real-workspace
journeys, docs build/link checks, and a first-time walkthrough. Target ten
minutes after dependencies are installed; record where newcomers get stuck.

### v0.6.0 — Diagrams that tell a story

- [ ] **5A. Show a useful scope by default (R9).** Add an explicit focused view
  for impact, a selected path, or one-hop neighbours; keep full-estate exploration
  available. Acceptance: StudentID's CSV fan-out is readable without fitting
  every unrelated system into the same viewport, and the view states its scope.
  Likely files: Atlas view state, graph component, and analysis-subgraph helper.
- [ ] **5B. Improve layout with fixtures (R9, R12).** Precompute adjacency and
  stable ordering; handle cycles/disconnected components deliberately; make
  spacing and node sizes reflect labels. Acceptance: chains, CSV fan-out, cycles,
  parallel relationships, isolated nodes, and duplicate/long names have stable
  placement without node overlap. Keep the existing layout if it meets the bar;
  evaluate another layout engine only against these fixtures.
  Likely files: `lib/layout.ts`, EntityNode, and layout fixtures/tests.
- [ ] **5C. Make reading and inspection accessible (R4, R9).** Improve label
  density, full-name disclosure, contrast, keyboard inspection, and reduced
  motion. Edge selection should open that relationship's evidence directly.
  Acceptance: the same flow is understandable at 100% and 200% browser zoom,
  at 1280px and 1920px widths, and through a keyboard-accessible text alternative.
  Likely files: graph nodes/edges, evidence panel, and design tokens.

**Verification:** browser screenshots of the named fixtures, keyboard and
contrast checks, reduced-motion checks, and focused layout tests. Have another
developer explain the Northstar flow from the diagram before reading the guide;
record ambiguous labels and improve them before release.

### v0.6.1 — Answers worth sharing

- [ ] **6A. Export the question being answered (R10).** Offer explicit scopes:
  filtered estate, selected path, or impact. Preview counts/limits before export;
  retain Mermaid/PlantUML and add a local SVG download for the focused diagram.
  Acceptance: exporting a path includes that path, and the SVG has readable
  labels, background/legend, correct arrows, and no dependency on a remote renderer.
  Likely files: export controls, diagram model/rendering, and export tests.
- [ ] **6B. Add a concise answer sheet (R10).** Export Markdown summarising the
  root/question, affected categories, representative chains, owners, confidence,
  review status, workspace/checkpoint context, and limits. Include redacted
  evidence references; make snippets/source-path disclosure an explicit choice.
  Acceptance: a recipient can assess the conclusion without opening Atlas, and
  an incomplete result never reads as exhaustive. Start with impact reports;
  reuse the structure for path reports in a separate slice.
  Likely files: report service, API/CLI adapters, export UI, and fixtures.
- [ ] **6C. Publish one excellent worked result.** Add a Northstar example that
  pairs a focused diagram with “Changing StudentID may affect…” and the source
  evidence behind the shared CSV junction. Acceptance: the example regenerates
  deterministically from the demo and contains no real estate data or secrets.
  Likely files: demo export script, docs/assets, and sharing guide.

**Verification:** reopen SVG at presentation size, render both text diagram
formats, compare report totals with the API, and test escaping/redaction with
adversarial labels. Validate empty, rejected, and truncated scopes. Exports
remain local and distinguish static-analysis findings from runtime certainty.

### v0.7.0 — A project others can understand

- [ ] **7A. Document one complete discovery (R11).** Create a contributor guide
  following one realistic fixture through extraction, identity resolution,
  reconciliation, evidence, influence traversal, API, and UI. Add a scanner recipe
  with an honest false-positive example. Acceptance: a contributor can locate
  the correct module and add a small scanner behavior without reading the whole
  repo. Likely files: contributor guide, architecture, and selected fixtures.
- [ ] **7B. Keep contracts from drifting (R4, R11).** Generate or mechanically
  check frontend domain/API types against Python contracts. Keep UI colours and
  icons in the frontend, and flow semantics in the domain. Acceptance: a backend
  field/enum change either updates the client contract or fails CI clearly.
  Likely files: schemas/domain, frontend types, a small contract script, and CI.
- [ ] **7C. Simplify the paths contributors change most (R11).** Move shared
  serialization out of API ownership, split crowded Atlas controls/view logic
  at their existing boundaries, and organise regression fixtures by behavior.
  Acceptance: services no longer import API helpers; refactors preserve public
  behavior and reduce the concepts needed to follow a scan or view update.
  Land each boundary change separately, keeping existing regression coverage.
  Likely files: serializers/impact, Atlas hooks/components, and focused test modules.

**Verification:** full checks and contract drift tests; ask a contributor to
complete the guide's small exercise. Review refactors separately from feature
changes. Preserve identity, manual edits, review verdicts, and migration behavior.

### v0.7.1 — Measured scale and durable history

- [ ] **8A. Establish a reproducible scale baseline (R12).** Add deterministic
  1k/10k-entity fixtures up to 50k relationships; measure scan/reconciliation,
  index/filter/search/impact, payload size, layout, and browser interactions.
  Record hardware/runtime and distinguish the full estate from the bounded
  rendered subgraph. Acceptance: published performance claims reproduce from
  checked-in commands; set regression budgets from measurements before optimising.
  Likely files: benchmark generator/runner, performance docs, and scheduled CI.
- [ ] **8B. Separate complete inventories from bounded diagrams (R5, R12).**
  Use paginated entity queries for inventories and explicit paging for impact
  members, so all active results are reachable. Make graph caps/configuration
  consistent. Remove demonstrated repeated scans, such as per-edge node lookup,
  before introducing caching. Acceptance: a 10k-entity estate has a complete
  searchable inventory and responsive focused graph, with exact totals and limits.
  Land inventory, impact paging, and measured renderer changes as separate slices.
  Likely files: entity/impact routes, schemas/client, lists, and graph renderer.
- [ ] **8C. Make history growth visible (R12).** Show checkpoint storage usage
  and document backup/restore. Add an opt-in retention/pruning workflow with
  a preview of lost comparison coverage; do not silently expire history.
  Acceptance: restoring a backup preserves edits, verdicts, and comparisons;
  pruning removes only explicitly selected history and leaves the active graph
  intact. Likely files: history service/CLI, settings/history UI, and restore tests.

**Verification:** before/after measurements, paging/limit regressions, real
browser interaction traces, and backup/restore against a populated older
database. Report measured ceilings instead of assuming every client can render
the full 50k-edge estate.

## How to keep these releases mini

Choose the next release, turn its slices into a short versioned spec under
`tasks/`, and update the active checklist. This roadmap is the forward plan;
existing versioned specs and completed checklists remain the release history.

Each slice should fit one focused review, normally touching two to five files.
Where a slice lists more surfaces, land producer/contracts first, then each
consumer with its regression. Split refactors from new behavior. If a theme
grows beyond a few slices, ship its useful core and move the rest to another
mini release. Use patch versions for compatible fixes; reconsider the proposed
version if implementation changes public contracts incompatibly.

Every release must satisfy [the release quality bar](docs/release-quality.md):

- [ ] Backend behavior tests and lint pass; frontend type checking/build pass.
- [ ] Relevant browser journeys pass, including a failure path and keyboard use.
- [ ] Diagram changes have reviewed screenshots at realistic scope and zoom.
- [ ] Existing workspace upgrades preserve manual knowledge and provenance.
- [ ] Documentation, screenshots, version metadata, and release notes agree.
- [ ] CI, documentation publication, and the shipped install path are checked.

## Later, when the core experience earns it

SQL Server Agent, GitHub Actions, and Azure Automation exports remain valuable
follow-ups. Take one scanner at a time with realistic fixtures, provenance,
confidence, and a worked example; verify that its added nodes remain readable.
Keep PostgreSQL, authentication, collaboration, and hosted operation for a
separate product decision with concrete users and deployment requirements.

Potential later presentation features include saved named views, comparison
overlays, PNG/PDF report output, and print/light themes. Revisit these after
focused diagrams and SVG/Markdown sharing have user feedback.

## Review validation and limits

- **Passed:** 155 backend tests, Ruff, frontend type checking, and production
  build. The build produced approximately 609 kB JavaScript / 190 kB gzip; this
  is a baseline, not proof of an interaction-performance problem.
- **Confirmed separately:** static-directory escape using a temporary marker,
  missing failed-scan history after an injected exception, a 30-hop result at
  a 25-hop limit, misleading reverse-flow export labels, and silent 50-member
  impact-group clipping. Existing passing tests do not cover these findings.
- **Environment recovery:** pytest used a workspace-local temporary directory
  and disabled its cache after sandbox permission errors; the frontend build
  passed outside the sandbox after esbuild was blocked from reading ancestors.
- **Not verified in this review:** browser appearance/interactions, accessibility,
  Docker build, fresh multi-platform installs, live CI/Pages state, and the
  claimed large-estate envelope. No browser connection was available. Visual
  proposals above are acceptance targets, not claims from observed screenshots.
- **Remaining warning:** the installed Starlette test client emits an `httpx`
  deprecation warning. Resolve through an isolated, compatibility-tested
  dependency change when pinning the tested environment; avoid bulk upgrades.

This review changes planning documentation only. R1–R5 remain implementation
work, with the security fix in v0.4.1 the immediate priority.
