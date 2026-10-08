# Security Model

Integration Atlas processes sensitive enterprise artefacts: scripts that
connect to production databases, config files with connection strings, scheduler
exports that name service accounts. The security posture is built around that
reality.

## Principles

### Local-first, by default

The application runs on the operator's machine. Data is stored in one SQLite
file under `~/.integration-atlas/` (or `ATLAS_DATA_DIR`).

* **No telemetry.** Nothing phones home.
* **No cloud upload.** No artefact, snippet or metadata leaves the machine.
* **No external AI APIs.** All analysis is local and deterministic.
* **No authentication layer.** The server binds to `127.0.0.1` by default and
  is meant to be reached by one person on one machine. If you expose it more
  widely, put it behind your own authentication — a future release may add
  first-class auth, but it is out of scope for Phase 1.
  The supplied Docker Compose file also publishes the port on loopback only;
  changing that binding exposes the unauthenticated API to other machines.

### Secrets never persist

Redaction happens **at the parser boundary**. Every persistable field —
snippet, description, location, name, qualified name, owner, technology and
every string in nested metadata — passes through `services/redaction.py`
before it can reach an ORM row, a log line, an API response or an export.
The API write paths and the exporters apply the same redaction.

The detector is deliberately over-eager. It matches:

* `password` / `passwd` / `pwd` / `passphrase`
* `secret` / `client_secret`
* `api_key` / `apikey` / `access_key`
* `auth_token` / `access_token` / `bearer` / `token`
* `private_key` / `privkey`
* connection-string `Password=` / `Pwd=`
* URL userinfo (`scheme://user:password@host`)
* AWS access key IDs
* JWTs
* `Bearer <token>` headers
* PEM private key blocks

Values are replaced with a stable mask that preserves *shape* but not content:

```text
Server=SQL-PROD-01;Database=FinancePro;Password=<redacted:credential>;
```

A `secret_events` row records that a redaction happened and where, so the
operator can see that masking occurred without ever seeing the secret.

**False positives are cheap; false negatives are not.** The detector will
occasionally mask a value like `password_policy=complexity` — that is why an
allowlist exists for known-safe keys (`token_type`, `key_file`,
`password_policy`, and similar). The allowlist is matched only to the key that
owns an assignment; a nearby safe key never hides a secret on another line.
Detection also covers JSON-style quoted keys and scheme-less
`user:password@host` values. See ADR-004.

Placeholder values (`<redacted>`, `${VAR}`, `{{var}}`, `%VAR%`, `none`,
`changeme`) are not treated as secrets, so already-clean artefacts are not
spammed with redaction events.

The test suite includes explicit leak tests: `tests/test_redaction.py` and
several cases in `tests/test_scanners.py` assert that a known secret string
does not survive anywhere in the persisted output.

### Nothing is executed

Scanners are static. They read text and match patterns. A scanned `.ps1`,
`.py` or `.sql` file is never imported, executed or evaluated. The application
does not shell out to discovered artefacts and does not render snippets as
HTML.

### Path handling

* Scans only read from a directory the operator explicitly passes to the CLI
  or the API.
* An optional allowlist (`ATLAS_SCAN_ROOT_ALLOWLIST`) constrains the API's
  `POST /api/scans` endpoint; paths outside it are rejected with `403`.
* Directory traversal skips noise directories (`.git`, `node_modules`,
  `.venv`, `__pycache__`, `dist`, `build`, …) and known-binary extensions.
* Files above `ATLAS_MAX_FILE_BYTES` (4 MB by default) are skipped rather than
  partially read.
* All paths are resolved with `Path.resolve()` before use.

### Malformed input

Every scanner is written to tolerate garbage: undecodable bytes fall back
through `utf-8-sig` → `utf-8` → `cp1252` → `latin-1` → `errors="replace"`;
malformed JSON or YAML produces a warning, not a crash; a file that makes one
scanner throw is recorded as a warning and the scan continues. The end-to-end
tests exercise this with binary-looking and truncated content.

### Logs

Scanner warnings and errors are stored as rows and shown in the UI. They
contain file paths and exception messages, never file contents. Because
snippets are redacted before persistence, a log line that quotes a snippet
cannot leak a secret.

## Threat model summary

| Threat | Mitigation |
|---|---|
| Credential leakage into the database | Redaction at the parser boundary + leak tests |
| Credential leakage through exports | Exporters serialise persisted rows, which are already redacted |
| Credential leakage through logs | Warnings carry messages, not snippets; snippets are redacted |
| Arbitrary file read via the API | Explicit path argument + optional allowlist + `resolve()` |
| Path traversal in scan roots | Allowlist check compares resolved paths |
| Code execution via a scanned artefact | Scanners never execute or import anything |
| Denial of service via huge files | Size cap + skip list |
| Data exfiltration | No network egress anywhere in the codebase |

## Reporting

Security issues should be reported through GitHub's private vulnerability
reporting for this repository. If that option is unavailable, open a minimal
issue asking for a private contact and keep vulnerability details out of it.
See [`SECURITY.md`](https://github.com/ikelaiah/integration-atlas/blob/main/SECURITY.md).
