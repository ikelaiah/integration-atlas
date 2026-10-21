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

## Candidate work

These are options to revisit for later releases. Select only the highest-impact
problem when planning each release.

- Make navigation, errors, and refresh predictable after edits, reviews, and
  scans.
- Rename, delete, or merge workspaces once people use several of them.
- Improve focused graph views, layout, keyboard access, and shareable results.
- Align API contracts and help contributors follow a discovery when real drift
  or maintenance friction appears.
- Measure larger estates before adding performance machinery, pagination, or
  history retention controls.

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
