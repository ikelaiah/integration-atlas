# Integration Atlas roadmap

Help people understand an integration estate, trust what Atlas finds, and explain
what could break when something changes. Prioritise a clear, evidence-backed
answer over adding more scanners or infrastructure.

This is a rolling plan based on the v0.4.0 repository review at `7b1aada`.
Versions are proposed milestones, not dates. Only the next two releases are
specified in detail; later work stays conditional until the nearer releases and
user feedback show what matters most.

## Product constraints

- Keep analysis local and static, with evidence and confidence visible.
- Keep SQLite and the existing React/FastAPI stack unless measured needs justify
  a change.
- Fix correctness and trust gaps before adding presentation features.
- Use the shared [release quality bar](docs/release-quality.md) for every release.

## v0.4.1 — Safe, trustworthy operations

Address three reproduced issues before diagram work:

- Keep SPA file serving inside the built frontend directory, including encoded
  paths and symlinks or junctions where supported.
- Preserve a failed scan record while rolling back partial discoveries and any
  success-only checkpoint; store a redacted, actionable error.
- Enforce path search depth as a hop limit, keep the visit budget separate, and
  report when the search budget is exhausted.

Acceptance: outside files are never served; a failed scan remains in history
without changing the graph; path results respect the requested depth and expose
search limits. Verify each with regression coverage and a built-app smoke check.

## v0.4.2 — Honest diagrams and counts

- Make diagram labels describe influence direction while preserving the stored
  relationship statement. Show both directions for bidirectional relationships.
- Report total, returned, and omitted members for capped impact groups and
  inventories, so partial results cannot look complete.
- Keep impact analysis and its visible graph scope consistent when filters or
  graph limits hide affected entities.

Acceptance: arrows, labels, counts, and omissions agree across the API, canvas,
and text exports. Verify every relationship type, capped results, and a filtered
StudentID impact flow in a browser.

## Later themes to revisit

These are candidates, not scheduled releases. Choose the next one only after
reviewing user feedback and the remaining highest-impact problems.

- Make navigation, errors, refresh, and workspace changes predictable.
- Make the first run clearly distinguish the Northstar demo from a real
  workspace.
- Improve focused graph views, layout, keyboard access, and shareable results.
- Help contributors follow a discovery through the code and keep API contracts
  aligned where drift is causing problems.
- Measure larger estates before adding optimisations, pagination, or history
  retention controls.

## Product decisions for later

Consider one additional scanner at a time, with realistic fixtures and a worked
example. PostgreSQL, authentication, collaboration, and hosted operation need
concrete users and deployment requirements before they become planned work.
Saved views, comparison overlays, and more export formats should wait for feedback
on focused diagrams and current sharing formats.

## Keeping the plan useful

Write a short implementation spec only when a release becomes the next priority.
Keep its acceptance criteria and verification focused on the user outcome; split
work where the code shows a real boundary. Update this roadmap when priorities
change, and use completed task checklists and release notes as the release history.

The release workflow takes its GitHub release title from the version tag. Keep
`.release-notes/vX.Y.Z.md` files as body text without a title heading.
