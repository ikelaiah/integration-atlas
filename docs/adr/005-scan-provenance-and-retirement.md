# ADR 005: Scan provenance, manual overrides and retirement

**Status:** Accepted · 2026-10

## Context

Reconciliation only ever *upserted*. Deleting a scanned script (or removing a
dependency from an edited file) and rescanning left its entities and
relationships active, so impact analysis kept reporting stale paths.

Rescans also overwrote manual corrections. A manual description survived one
rescan but the entity's `source_kind` was flipped to `discovered`; the next
rescan then overwrote the description. Editing a discovered entity through the
API gave it no protection at all.

## Decision

### Provenance

Evidence already records the artefact (`source_path`) that produced a
discovery. That is the provenance used for reconciliation — no separate
bookkeeping table is required.

### Manual overrides

* `entities.manual_fields_json` lists the fields a human edited.
* The API `PATCH /entities/{id}` redacts inputs, records each edited field,
  and sets `source_kind = manual`.
* On upsert, discovery never overwrites a field listed as manual, and a
  `manual` entity is never downgraded to `discovered`.
* For backwards compatibility, a manual entity with no explicit field list
  falls back to protecting `description` and `owner`, matching ADR-003.

### Retirement

After a scan of root *R*, each previously-discovered entity/relationship
under *R* that was **not** observed by the scan is retired
(`is_active = false`) only when every one of its evidence rows confirms the
artefact is gone:

* the source file no longer exists, or
* the source file was parsed successfully this scan but no longer yields the
  discovery (a dependency removed from an edited file).

The following are never treated as deletions:

* files that were skipped, unreadable or made a scanner throw;
* manual rows;
* discoveries also supported by evidence outside *R* (an overlapping root or a
  shared entity).

Retired rows are kept for history but excluded from the graph, search,
overview, risk analysis and exports.

### Deterministic resolution

`apply_many` persists **all** entities before resolving **any** relationship.
Previously, resolution could depend on which file happened to be visited
first, so a rescan could resolve a reference to a different same-named entity
and create a duplicate edge.

## Schema changes

| Table | Column | Purpose |
|---|---|---|
| `entities` | `is_active` (bool, default true) | soft retirement |
| `entities` | `manual_fields_json` (JSON list) | per-field manual overrides |
| `relationships` | `is_active` (bool, default true) | soft retirement |

The project has no migration *tool*, so `init_db` performs a small,
idempotent, data-preserving upgrade in `atlas.db.migrate_schema`:
`Base.metadata.create_all` creates missing tables, then any missing column in
the table above is added with `ALTER TABLE … ADD COLUMN … DEFAULT …`. Existing
rows (including manual knowledge) are untouched and receive the default, and
running it again is a no-op. Non-SQLite backends are skipped until a real
migration tool is introduced.

## Consequences

* Deleted files, removed dependencies, overlapping roots, shared entities,
  manual rows and partial scan failures all behave correctly and are covered
  by regression tests.
* Retirement is conservative: it prefers a stale row over accidentally
  deleting a real discovery because a file could not be read.
