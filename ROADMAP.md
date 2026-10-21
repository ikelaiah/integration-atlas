# Integration Atlas roadmap

Help people understand an integration estate, trust what Atlas finds, and see
what could break when something changes. Keep the roadmap focused on user
problems; choose the next release scope only when evidence supports it.

## Priorities

- Keep analysis local and static, with evidence, confidence, and result limits
  clear.
- Fix correctness and trust gaps before adding presentation features or scanners.
- Keep SQLite and the current React/FastAPI stack until measured needs justify a
  change.
- Use the shared [release quality bar](docs/release-quality.md) for every
  release.

## Recent releases

**v0.6.0** keeps the Northstar demo separate from people's own estates. First
run offers a choice between the demo and a scan, scans go into named
workspaces, the sidebar switches workspaces, and a demo reset keeps any scan
results it finds in a separate workspace instead of deleting them. See the
[v0.6.0 specification](tasks/v0.6.0-spec.md).

**v0.5.1** clarifies local versus server collection privileges and adds Windows
and Linux collectors for scheduler definitions and supported source/config
files from explicit roots.

**v0.5.0** made graph navigation predictable: drags pan the canvas without
moving or selecting layout nodes, selection preserves the current viewport,
and zoom and fit controls perform their labelled actions. See the
[v0.5.0 specification](tasks/v0.5.0-spec.md).

## Planned releases: v0.7.0 to v0.15.0

This sequence reflects the evidence as of v0.6.0. Recheck it before writing
each release's spec: a release moves, shrinks, or drops when its evidence
changes, and later releases are less certain than earlier ones. A release
marked **gated** happens only when its condition is met; otherwise the next one
moves up.

**v0.7.0 — Current risks and honest failures.** Saved risk findings are only
recalculated after a scan or demo load. In the demo, setting an owner on
"Archive cleanup" dropped Overview to 8 findings while Risks still listed 9,
including "has no recorded owner". A failed risk request shows "No findings",
and Overview, entity lists, impact, and search hide errors the same way.
Recalculate findings in the same save as edits, review decisions, and manual
adds or deletes, refresh them in the app, and show failures with Retry.

**v0.8.0 — Try Atlas on the documentation site.** Today, trying Atlas means
cloning, installing Python and Node, and building the frontend. Publish the
Northstar demo at `ikelaiah.github.io/integration-atlas/demo/`, running the
real Atlas API inside the visitor's browser with Pyodide. Nothing is sent
anywhere, and changes reset on reload. A spike after v0.6.0 ran the app unchanged in
Pyodide 314 (demo load, overview, graph, impact, and risks), apart from
running FastAPI's threadpool calls inline. It needs pinned packages, a
prebuilt demo database instead of seeding in the browser (about 7 seconds in
the spike), a loading screen, and a CI smoke test. The first visit downloads
about 18 MB (roughly 7–8 MB compressed), cached afterwards. **Depends on**
a DocSprout release that can copy a pre-built static folder into the site, so
the managed Pages workflow keeps publishing both.

**v0.9.0 — Rename and delete workspaces.** v0.6.0 keeps mixed demo data in
`(kept …)` workspaces, and scans can create workspaces under a mistyped name,
but no workspace can be renamed or deleted. Add rename, and delete with a
confirmation that states what is removed. The demo itself can only be reset.

**v0.10.0 — Share an impact answer.** "If I change this, what breaks?" is the
question Atlas exists to answer, but the impact panel cannot export its result.
Export an impact result as Markdown and CSV from the web app and from
`atlas impact`, keeping the root, direction, depth, confidence, evidence
references, and any omissions.

**v0.11.0 — Measure larger estates.** The README claims a design target of
10,000 entities and 50,000 relationships, but no test measures it. Scans run
inside one request with no progress. Add a synthetic estate generator and
repeatable timings for scan, graph, impact, search, and graph rendering. Then
publish the results and correct the README claim if needed.

**v0.12.0 — Fix the worst measured bottleneck (gated).** Only if v0.11.0 shows
an operation too slow for that size. If scans are the problem, run them in the
background with progress; if rendering is, narrow what the canvas draws.

**v0.13.0 — Focused views and keyboard access.** Graph nodes cannot be reached
or selected from the keyboard, and the default view can hold up to 2,000
nodes. Add a neighbourhood view around a selected entity and keyboard
navigation of nodes, the detail panel, and impact results.

**v0.14.0 — SQL Server Agent jobs.** The first scheduler scanner beyond Task
Scheduler and cron, reading exported job scripts statically, with realistic
fixtures and a worked example.

**v0.15.0 — One source for API types.** The frontend's API types are written by
hand and can drift from the backend schemas. Generate them from the OpenAPI
schema, check for drift in CI, and add a contributor guide that follows one
discovery from scanner to UI.

## Not planned yet

- GitHub Actions or Azure Automation workflow scanning, after v0.15.0. Choose
  one by which exports people ask for, with fixtures and a worked example.
- Merging workspaces and moving discoveries between them.
- Pagination and history retention controls, unless v0.11.0 measurements
  show a need.
- Saved views, comparison overlays, and more export formats.
- PostgreSQL, authentication, collaboration, and hosted operation. The
  v0.8.0 demo runs in the visitor's browser; it is not a hosted Atlas.

## Guardrails

Add one scanner at a time with realistic fixtures and a worked example.
PostgreSQL, authentication, collaboration, and hosted operation need concrete
users and deployment requirements before they become planned work. Saved views,
comparison overlays, and more export formats should wait for feedback on focused
diagrams and current sharing formats.

Write a short implementation spec only when a release becomes the next
priority. Keep acceptance criteria and verification tied to user outcomes. Use
completed task checklists and release notes as release history.

The release workflow uses the version tag as the GitHub release title. Keep
`.release-notes/vX.Y.Z.md` files as body text without a title heading.
