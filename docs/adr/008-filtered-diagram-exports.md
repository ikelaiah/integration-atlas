# ADR 008: Shared graph filtering and diagram exports

## Context

The first Atlas graph could filter entity type and confidence, but its type
buttons were counted from the filtered result. A selected type made other
choices disappear. Path selection also depended on the loaded graph, which
could hide entities through filtering or truncation. Operators needed to share
readable diagrams of a chosen view.

## Decision

The graph API applies entity, environment, confidence, relationship, review
status and text filters on the server. It returns facet counts from the full
active workspace separately from the bounded filtered result. Rejected edges
remain hidden unless selected. The path dialog uses workspace search instead
of loaded graph nodes, and path results name their traversal direction.
Relationship and review filters keep only connected endpoints. Text search
retains matching nodes and, when an edge filter is active, their connected
neighbors so the matching relationship remains visible.

A shared diagram renderer accepts node and influence-edge values. The filtered
HTTP export uses the same graph query and limit as the Atlas view. CLI exports
use the same renderer over the full active, non-rejected graph. Diagram labels
are redacted and escaped at the export boundary, with stable opaque aliases
for node identifiers.

## Consequences

Facet counts are stable while filtering, though they describe the workspace
rather than the current result. Graph queries build an additional full index
to include rejected edges in those counts. A path can overlay nodes hidden by
filters; diagram export remains scoped to the filters and excludes that
temporary overlay. No storage migration or external rendering service is
required.
