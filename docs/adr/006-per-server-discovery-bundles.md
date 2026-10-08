# ADR 006: Per-server discovery bundles

**Status:** Accepted · 2026-10

## Context

Scheduler exports are collected machine by machine. Without metadata, Atlas
cannot tell `nightly-export` on `APP01` from `nightly-export` on `APP02`, and
the natural-key fingerprint would merge them. It must also never *guess* the
execution host from a task's `Author`, `UserId`, `URI`, or a hostname that
merely appears in a command.

## Decision

A **bundle** is a directory containing a `server.json` manifest:

```json
{
  "hostname": "APP-SERVER-01",
  "fqdn": "app-server-01.corp.example",
  "os": "windows",
  "environment": "production"
}
```

Only `hostname` is required. `server.json` is metadata, not a config file to
mine: no scanner claims it.

### Scoping

* Task/cron identities are scoped by **execution server and full task path**
  (`<server>::<uri path>` / `<server>::<schedule leaf>`).
* Local script/file identities are scoped by **execution server and original
  path** (`<server>::<path>`).
* The server scope is folded into the entity fingerprint, so identical names
  and paths on two servers never merge.
* Remote dependencies (a database host, an API, a UNC share, a URL) are *not*
  scoped and therefore merge across servers — they are the same shared
  dependency.
* References are resolved within server context: a job's `RUNS` target
  resolves to the local script on the same server, not another server's
  same-named script.

### Relationships

Each scheduled job/script in a bundle gets a `job --RUNS_ON--> server` edge.
`RUNS_ON` has influence `server -> job`, so a server change correctly impacts
the jobs it hosts. Execution hosts stay separate from dependency hosts: a
script that connects to a host still gets its own `CONNECTS_TO` dependency
host, distinct from the execution server entity.

### Missing metadata

An import with no `server.json` still works; the job simply has no
`server` metadata, is not scoped, and gets no `RUNS_ON` edge. The execution
server is effectively **unknown** rather than invented.

### Cron formats

* System crontabs (`/etc/crontab`, `/etc/cron.d/*`) have an optional user
  column; the user is parsed from it.
* User crontabs (`/var/spool/cron/crontabs/<user>`) have **no** user column;
  the exported user is captured explicitly from the artefact context, and the
  line is parsed without a user column.

### Collection is read-only

Collection scripts only copy/read/export artefacts. Discovered jobs are never
executed, imported or evaluated. See `docs/server-bundles.md` for Windows and
Linux collection examples.
