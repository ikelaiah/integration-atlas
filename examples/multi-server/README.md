# Multi-server example bundles

Two realistic per-server bundles for exercising the server-provenance feature:

```bash
atlas scan run ./examples/multi-server
```

* `windows-app01/` — a Windows Task Scheduler export plus its local script.
* `linux-app02/` — a system crontab, a user crontab (no user column) and its
  local script.

Each bundle's `server.json` declares its execution host. The two bundles share
the remote `SHARED-DB-01` dependency, which intentionally merges into a single
entity, while the local scripts and jobs stay scoped to their own server.

Collection guidance lives in
[`docs/server-bundles.md`](../../docs/server-bundles.md). Nothing in a bundle
is ever executed.
