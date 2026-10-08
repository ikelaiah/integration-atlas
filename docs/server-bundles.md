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

## Collection is read-only

Every command below **only reads and exports** artefacts. Nothing is executed,
imported, or evaluated.

### Windows — Task Scheduler

Run on the target host (e.g. from an admin shell) and write into the bundle:

```powershell
$bundle = "C:\collect\APP-SERVER-01"
New-Item -ItemType Directory -Force $bundle\windows\tasks | Out-Null
New-Item -ItemType Directory -Force $bundle\scripts | Out-Null

@{
  hostname    = $env:COMPUTERNAME
  fqdn        = [System.Net.Dns]::GetHostEntry($env:COMPUTERNAME).HostName
  os          = "windows"
  environment = "production"
} | ConvertTo-Json | Set-Content -Encoding UTF8 "$bundle\server.json"

# Export each task definition as XML (does not run anything).
Get-ScheduledTask | ForEach-Object {
  $safe = ($_.TaskPath + $_.TaskName) -replace '[\\/:*?"<>|]', '_'
  Export-ScheduledTask -TaskName $_.TaskName -TaskPath $_.TaskPath |
    Set-Content -Encoding UTF8 (Join-Path $bundle\windows\tasks "$safe.xml")
}

# Copy referenced local scripts (read-only).
Copy-Item C:\integrations\*.ps1 -Destination "$bundle\scripts" -ErrorAction SilentlyContinue
```

### Linux — cron

Run on the target host and write into the bundle:

```bash
BUNDLE=/collect/LINUX-01
mkdir -p "$BUNDLE/linux/cron.d" "$BUNDLE/linux/crontabs" "$BUNDLE/scripts"

cat > "$BUNDLE/server.json" <<JSON
{
  "hostname": "$(hostname)",
  "fqdn": "$(hostname -f 2>/dev/null || hostname)",
  "os": "linux",
  "environment": "production"
}
JSON

# System crontabs (optional user column).
cp /etc/crontab "$BUNDLE/linux/cron.d/system-crontab" 2>/dev/null || true
cp /etc/cron.d/* "$BUNDLE/linux/cron.d/" 2>/dev/null || true

# Per-user crontabs: filename is the user; the lines have NO user column.
for user in $(cut -d: -f1 /etc/passwd); do
  line=$(crontab -l -u "$user" 2>/dev/null) && printf '%s\n' "$line" > "$BUNDLE/linux/crontabs/$user"
done

# Copy referenced local scripts (read-only).
cp /opt/integrations/*.py "$BUNDLE/scripts/" 2>/dev/null || true
```

## Security notes

* `server.json` is metadata; Atlas does not treat it as a config file and never
  mines it for entities.
* Bundle locations never cause execution of the jobs they describe.
* Secrets in task arguments, cron commands, config or script snippets are
  redacted at the parser boundary before persistence (ADR-004).
