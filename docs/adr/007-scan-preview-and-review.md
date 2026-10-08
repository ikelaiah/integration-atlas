# ADR 007: Transactional scan preview and review decisions

## Context

An operator needs to see the likely graph changes before applying a rescan.
The existing scanner writes through SQLAlchemy as it normalises results, and
the UI had no way to inspect a proposed diff. Manual entity fields and
relationship review status already persisted in SQLite.

## Decision

Preview runs the normal scan pipeline inside a database savepoint and rolls it
back after comparing graph snapshots. Apply runs the pipeline again and stores
its own actual diff in `Scan.diff_summary`. The two results may differ when
source files change. Diff counts include all changed graph rows; the API lists
at most 100 names and types. Scan history uses the same progress response as
the individual scan endpoint.

The review API filters active relationships by verdict and returns their
evidence. A decision updates `review_status` and can add a redacted manual-note
evidence row in the same transaction. Rescans preserve the verdict and note.
Rejected relationships remain in storage for review history but stay out of
the default graph.

## Consequences

Preview does the same parsing work as apply, so reviewing and applying a scan
costs two passes. No new schema is needed. The savepoint guarantees that
preview does not leave graph, evidence or scan rows behind in the normal
single-process SQLite deployment.
