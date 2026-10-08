# ADR 001: SQLite as the default store

**Status:** Accepted · 2026-04

## Context

Integration Atlas is local-first. A developer should be able to clone the
repository and have a working application in a minute, with no database to
install or configure. At the same time the persistence layer must not paint us
into a corner if a team later wants a shared PostgreSQL instance.

## Decision

Use SQLite by default through SQLAlchemy 2.0, with models written in a
dialect-neutral way. The connection pragmas that are SQLite-specific live in
one function (`db.py::_configure_sqlite`) and nothing else in the codebase
knows which engine is in use.

Identifiers are text UUIDs rather than integer autoincrements.

## Consequences

* Zero-setup local use. The database is one file under `~/.integration-atlas`.
* Moving to PostgreSQL is a `ATLAS_DATABASE_URL` change plus a migration step.
* Text UUIDs cost a little index space and make manual SQL inspection less
  ergonomic than integers would be. That trade is worth it: rows can be
  exported, merged across workspaces and diffed without ID collisions.
* No ORM abstraction layer on top of SQLAlchemy. That would be an abstraction
  over an abstraction; the cost of adding it now outweighs the hypothetical
  benefit.

## Alternatives considered

* **PostgreSQL from the start.** Rejected: it adds a service to install for
  the primary use case, which is a single operator scanning a folder locally.
* **A pure in-memory model with export only.** Rejected: manual edits, review
  state and scan history need to persist.
* **An ODM/abstraction over SQLAlchemy.** Rejected as premature.
