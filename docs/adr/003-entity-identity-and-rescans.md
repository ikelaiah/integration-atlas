# ADR 003: Entity identity and rescan reconciliation

**Status:** Accepted · 2026-04

## Context

Discovery runs repeatedly as more folders are scanned. Two problems follow:

1. The same artefact is described differently depending on who found it. A
   directory walk yields an absolute path; a Task Scheduler export yields
   `C:\integrations\student\export_students.ps1`; a config file may yield a
   POSIX path. Naive identity creates three "entities" for one script.
2. Rescans must not destroy manual knowledge. If a human corrected an owner or
   confirmed a relationship, a later scan must not silently undo it.

## Decision

### Natural keys

Every entity carries a `fingerprint`:

```text
entity_type | normalised identity | path tail
```

Path-shaped identities and locations are normalised to their **last three
segments** after stripping drive letters and UNC prefixes. Two references to
`export_students.ps1` therefore unify regardless of how they were written,
while same-named files in genuinely different folders stay distinct.

The normaliser resolves scanner references through a **type-aware** index:
when a candidate carries a `target_type_hint` (a `SCHEMA`, a `TABLE`, a
`FILE`), only entities of that type are considered. Ties break on
`(entity_type, qualified_name, id)` so resolution is deterministic across
scans. This matters because `Student` the schema and `student` the directory
are different things that happen to share a name.

### Reconciliation

A rescan **upserts by fingerprint**. It reports `added`, `updated`,
`unchanged` and `removed` rather than deleting and recreating. Manual rows
(`source_kind = manual`) have their owner and description preserved on update.

### Unresolved references

A reference the normaliser cannot resolve becomes an entity with
`is_missing = true` at low confidence. That is information, not an error:
"something depends on an artefact nobody found" is exactly the kind of thing
this product exists to surface.

## Consequences

* Rescans are idempotent. The test suite asserts a second scan adds zero
  entities and zero relationships.
* Same-named files in different folders remain distinct, which is correct.
* Two references that differ only within their last three path segments will
  merge. For file artefacts that is the desired behaviour; for other entity
  types the `qualified_name` carries the real identity and is compared in full.
* Manual edits survive discovery. That is a hard requirement — automatic
  discovery will never be perfect and human knowledge must not be disposable.

## Alternatives considered

* **Content hashing.** Rejected as the primary key: two different files can
  share content, and a one-character edit to a script would orphan all its
  relationships.
* **Delete-and-recreate per scan.** Rejected: it destroys review state and
  makes the diff view meaningless.
* **Exact-path identity.** Rejected: it is what produced the three-entities-
  for-one-script bug this ADR exists to prevent.
