# Per-server discovery bundles

Atlas can attribute scheduler exports and local scripts to the machine that
executes them — without ever inferring that from a task's `Author`, `UserId`,
`URI` or a hostname that appears in a command. You do that by collecting each
machine's artefacts into a **bundle** with a small manifest.

See [`docs/adr/006-per-server-discovery-bundles.md`](adr/006-per-server-discovery-bundles.md)
for the decision record.

## Bundle format

```text
bundles/
  APP-SERVER-01/
    server.json                 # execution-server manifest (required metadata)
    windows/tasks/*.xml         # Task Scheduler exports   (Windows)
    linux/cron.d/*              # system crontabs          (Linux)
    linux/crontabs/<user>       # per-user crontabs        (Linux)
    scripts/                    # local scripts referenced by the jobs
    config/                     # optional config files
  LINUX-01/
    server.json
    ...
```

`server.json`:

```json
{
  "hostname": "APP-SERVER-01",
  "fqdn": "app-server-01.corp.example",
  "os": "windows",
  "environment": "production"
}
```

| Field | Required | Meaning |
|---|---|---|
| `hostname` | yes | Execution server identity (the scope key) |
| `fqdn` | no | Fully-qualified name, for display |
| `os` | no | `windows` / `linux` / other |
| `environment` | no | `production` / `test` / `development` |

Nested bundles are allowed: an inner `server.json` owns everything below it.

Then point a scan at the bundles directory:

```bash
atlas scan run ./bundles
```

## What Atlas creates

* A `server` entity for each declared host.
* For each task/cron job in the bundle, `job --RUNS_ON--> server`.
* Local scripts/files scoped to the server, so identical names/paths on two
  machines stay distinct.
* Remote dependencies (DB hosts, APIs, UNC shares, URLs) are **not** scoped and
  merge across servers.
* A bundle with no `server.json` still imports cleanly; its jobs simply have
  the execution server recorded as unknown and no `RUNS_ON` edge.

## Collect a server bundle

The included collectors **only read and copy** files and export scheduler
definitions. They never run discovered jobs or scripts. Run a collector on each
source server, then transfer the resulting bundle to the machine running Atlas.
Pass every directory that contains integration scripts or configuration as a
source root. The collector copies Atlas-supported text file types from those
roots and preserves their relative paths; it does not search the whole disk or
guess where an integration lives.

Running Atlas itself does not require elevated privileges when the files being
scanned are readable by your account. Collecting a complete set of scheduler
definitions may require administrator access on Windows or root access on
Linux, especially for tasks or crontabs owned by other accounts. Without those
permissions, collect what you can read; inaccessible items may be missing.

### Windows — Task Scheduler and source files

From the repo checkout on the target host, run PowerShell and provide the real
integration directories. Add one `-SourceRoot` path for each directory. Use an
admin shell if needed to export all scheduled tasks and read every source file:

```powershell
& .\scripts\collectors\collect-windows.ps1 `
  -OutputDirectory 'C:\collect\APP-SERVER-01' `
  -SourceRoot 'C:\Integrations', 'D:\BatchJobs' `
  -Environment 'production'
```

This exports Task Scheduler definitions and copies supported source/config
files under each supplied root. Replace the example paths and environment with
values from your server.

### Linux — cron and source files

From the repo checkout on the target host, provide every integration source
directory. Use `sudo` to collect all users' crontabs and files that your account
cannot read:

```bash
sudo bash ./scripts/collectors/collect-linux.sh \
  /collect/LINUX-01 \
  /opt/integrations /srv/batch-jobs
```

Replace the example paths with the directories used on your server. To set a
non-production environment, pass it through `sudo env`, for example:
`sudo env ATLAS_ENVIRONMENT=development bash ./scripts/collectors/collect-linux.sh ...`.
This collector exports cron definitions; systemd timers and other schedulers
are not currently imported by Atlas. Use the
[supported scanners](../README.md#supported-scanners) as the coverage guide.

## Security notes

* `server.json` is metadata; Atlas does not treat it as a config file and never
  mines it for entities.
* Bundle locations never cause execution of the jobs they describe.
* Bundles contain copies of source and config files and may include credentials.
  Store and transfer them securely, and remove them when no longer needed.
* Secrets in task arguments, cron commands, config or script snippets are
  redacted before Atlas persists scan findings (ADR-004); the original bundle
  files remain unredacted.
