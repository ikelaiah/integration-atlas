# ADR 009: Persist graph checkpoints with applied scans

## Context

The v0.2 scan diff records exact counts but bounds its named change list to
100 rows. It cannot reconstruct a graph at an arbitrary older scan, especially
after later edits, retirement or another scan. Comparing old scan diff totals
would count intermediate churn instead of net graph change.

## Decision

Each applied scan stores compact before and after active graph states in a
`scan_snapshots` row, in the same transaction as the scan. The shared scanner
runner captures these for CLI and HTTP scans. Preview uses a savepoint, so its
row rolls back with the preview. The new table is additive for existing SQLite
databases; older scans are never assigned a fabricated checkpoint.

Snapshots contain graph identity and basic display/review attributes. They
exclude evidence, snippets, paths and metadata, and redact captured text again.
Comparison reads two ordered checkpoints in one workspace, counts all net
changes and pages a deterministic detail list. It never runs a scanner or
mutates the live graph. A changed field is compared by stable row ID; an entity
rename does not itself count as a changed relationship.

## Consequences

Storage grows with the size of the active graph for each applied scan. This is
the cost of accurate historical comparison; snapshot payloads remain much
smaller than source or evidence records. Existing scans retain their original
per-scan diff. A first post-upgrade scan supplies its own before checkpoint,
so users can compare that scan without migrating old history. Concurrent scans
should be avoided because independently captured workspaces can overlap in
time; the API requires an ordered pair of checkpoint timestamps.
