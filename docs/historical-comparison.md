# Compare graph history

Atlas saves the active integration graph immediately before and after each
applied scan. These checkpoints make it possible to answer what changed across
one scan or several scans without reading the source files again. They include
active entities and relationships, including relationships marked rejected.
They contain names and basic graph attributes, with redaction applied again at
capture; they do not copy evidence, snippets, source paths or metadata.

## Compare your first scan

1. Open the local app with `atlas serve`, then open **Scans**.
2. Preview a folder, then choose **Apply scan**. Preview does not create a
   checkpoint. An applied scan saves **Before** and **After** checkpoints.
3. In **Compare graph history**, leave the latest scan's **Before** and
   **After** selected. The cards show entity and relationship counts at each
   end, plus added, changed and retired totals.
4. Expand a changed row to inspect its old and new values. Filter by entity or
   relationship, action, or name. **Load more changes** pages through the
   complete result when the initial list is bounded.

For a concrete example, scan `examples/northstar`, edit a copy of one input
file, and scan the same folder again. Choose **After** for the first scan and
**After** for the second to inspect the net graph change. Atlas compares saved
states: a row added and then retired between the chosen points does not appear
as a net change. The individual scan diff remains available in **Scan history**.

## What counts as history

Checkpoints begin with scans applied on v0.4.0 or later, through either the web
app or CLI. Earlier scans retain their original per-scan diff, but Atlas cannot
rebuild their full historical graph from that bounded list. A fresh applied
scan captures its own before and after states, including the graph that existed
before upgrading. Seeding the demo does not create a scan checkpoint; scanning
the Northstar example does.

An entity edited or a relationship reviewed between scans appears in the
**Before** checkpoint of the next scan. The current Atlas graph continues to
show today's state; viewing history does not change it. A snapshot captures
only active rows and relationship endpoints that are active at that moment.
If a comparison has no net changes, the two selected graph states are equal
for the captured attributes.

The comparison API is available locally at `GET /api/scans/checkpoints` and
`GET /api/scans/compare`. It requires a workspace and ordered checkpoint pair,
returns exact totals, and pages the detailed changes. No remote service or
source-server scanning agent is involved.
