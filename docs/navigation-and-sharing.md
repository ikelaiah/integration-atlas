# Navigate and share an integration map

The interactive Atlas runs locally with `atlas serve`. GitHub Pages hosts this
guide, while graph data stays in your local SQLite database.

## Narrow the graph

Open **Atlas** and expand **Filters**. Choose one or more entity types,
environments, relationship types or review statuses; optionally set a minimum
confidence and search names, qualified names, technologies or owners. The
numbers on filter choices describe the full active workspace, so choices do
not disappear when the view narrows. **Clear all** restores the default graph.
Relationship filters show their connected entities. Adding text search keeps
matching entities and their neighbours along the selected relationships.
Rejected relationships are hidden until you explicitly select that review
status. A large graph is capped at 2,000 displayed nodes by default, and Atlas
labels a limited view.

The entity inventories report when this graph cap omits entities; local text
filtering only searches the entities returned for the view. Impact analysis runs
over the workspace independently of visual filters and overlays its bounded
analysis subgraph, so affected entities hidden by a filter can still be seen.
Impact groups show how many entries are listed and omitted. If the analysis hits
its own result limit, counts are lower bounds.

## Find a route through the estate

Choose **Find path**, search for the source and destination, then choose
**Find path** again. Search includes all active workspace entities, including
those hidden by visual filters. Use **Swap endpoints** to reverse the query.
The result reports a downstream influence route, an upstream route, or a
connection that mixes directions. A mixed route shows structural connectivity;
it is not an end-to-end impact path. The exact path is overlaid on the graph,
and the side panel shows each relationship and its confidence. When no path is
found, Atlas explains whether the hop limit or visit budget prevented a
conclusion. **Change** reopens the endpoint selector.

For example, in the Northstar demo, search for `StudentID` and
`EnrolmentPortal` to trace how a data change reaches the portal.

## Export a diagram

With a graph view selected, choose **Export** and download **Mermaid (.mmd)**
or **PlantUML (.puml)**. The download uses the current filters and graph cap;
its first comment records node and edge counts and whether it was truncated.
Temporary path overlays are excluded from the filtered graph export. Labels
are redacted, escaped and limited in length. The diagrams include names, types
and influence-direction labels, without source snippets or evidence. Reverse-
flow relationships point toward the affected entity; `calls` uses arrows in
both directions. The stored statement remains available in relationship details.

The CLI exports the full active, non-rejected workspace:

```bash
atlas export -f mermaid -o atlas.mmd
atlas export -f plantuml -o atlas.puml
```

Mermaid text can be placed in a Markdown `mermaid` code block. PlantUML text
can be rendered by any PlantUML-compatible tool. Neither export runs scanned
source files or sends your estate to a remote service.
