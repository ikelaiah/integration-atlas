# ADR 002: Relationship flow semantics

**Status:** Accepted · 2026-04

## Context

A relationship like `student_export.py READS_FROM Student.Person` is stored in
a natural direction: the statement reads correctly in English. But the product
question is the opposite one — *if I change `Student.Person`, what breaks?* —
and that propagates from the table to the script.

Naively traversing stored edges gives backwards results for exactly the
relationships that matter most (`reads_from`, `consumes`, `uses_column`).

## Decision

Every relationship type declares a **flow**:

* `Flow.FORWARD` — influence runs `source → target`
* `Flow.REVERSE` — influence runs `target → source`
* `Flow.BOTH` — influence runs both ways

The graph index expands each relationship into one or two **influence arcs**
and traversal walks those, not the stored edges.

`calls` is `BOTH`. A caller and a callee are genuinely coupled: changing the
caller can break the callee's contract, and changing the callee breaks the
caller. Everything else is single-direction.

## Consequences

* "What could break if I change X?" is `downstream` — one traversal.
* "What does X need?" is `upstream` — the reverse traversal.
* The UI draws arrows in influence direction with an arrow-facing label
  (`read by`, `consumed by`, `hosts`) so the map reads as a data-flow diagram
  while the stored statement still reads as English.
* Adding a relationship type requires choosing a flow. That is a one-line,
  testable decision recorded in `RELATIONSHIP_FLOW`.

## Alternatives considered

* **Store edges in influence direction only.** Rejected: the stored statements
  stop reading as English (`Person READS_FROM student_export.py`), which makes
  evidence panels and exports confusing.
* **Traverse both directions for impact.** Rejected: "what could break" would
  become "everything connected to this", which is not an answer.
* **Two edge tables, one per direction.** Rejected: twice the surface area for
  the same information.
