# Domain Model

The vocabulary of Integration Atlas. Everything here is defined in
`backend/atlas/domain.py` and mirrored in `frontend/src/lib/types.ts`.

## Entity types

| Type | Example | Notes |
|---|---|---|
| `system` | LegacySIS | A business system as the organisation thinks of it |
| `application` | Student Services Console | Deployable software |
| `external_service` | LearningCloud | SaaS or partner system outside your control |
| `integration` | Student extract → EnrolmentPortal | A named end-to-end flow |
| `server` | APP-SERVER-01 | Physical/virtual host |
| `database` | LegacySIS, FinancePro | A database or instance |
| `schema` | `Student`, `mart` | Namespace inside a database |
| `table` | `Student.Person` | |
| `column` | `Student.Person.StudentID` | The unit impact analysis is usually run on |
| `script` | `export_students.ps1` | Any executable artefact |
| `scheduled_job` | `nightly-student-export` | cron, Task Scheduler, SQL Agent |
| `api` | EnrolmentPortal REST API | A service surface |
| `endpoint` | `POST /applications/import` | A specific route |
| `file` | `students.csv` | Data in motion |
| `directory` | `/integrations/student/` | Drop folders, shares |
| `sftp_location` | `SFTP-01:/outbound/learning` | Managed file transfer |
| `queue` | | Message broker topic/queue |

## Relationship types and flow

A relationship is stored as `source --type--> target` and reads as an English
sentence: `export_students.ps1 READS_FROM LegacySIS.Student.Person`.

Each type also declares an **influence direction** — which way a change
propagates:

| Type | Reads as | Influence flows | Arrow label |
|---|---|---|---|
| `reads_from` | A reads from B | B → A | read by |
| `writes_to` | A writes to B | A → B | writes to |
| `calls` | A calls B | **both** | couples |
| `runs` | A runs B | B → A | run by |
| `runs_on` | A runs on B | B → A | hosts |
| `depends_on` | A depends on B | B → A | required by |
| `produces` | A produces B | A → B | produces |
| `consumes` | A consumes B | B → A | consumed by |
| `transfers_to` | A transfers to B | A → B | transfers to |
| `imports_from` | A imports from B | B → A | imported by |
| `exports_to` | A exports to B | A → B | exports to |
| `triggers` | A triggers B | A → B | triggers |
| `uses_table` | A uses table B | B → A | used by |
| `uses_column` | A uses column B | B → A | used by |
| `connects_to` | A connects to B | B → A | linked to |

`calls` is bidirectional on purpose: a caller and a callee are genuinely
coupled in both directions, so a change on either end can break the other.

**Impact analysis** ("what could break if I change X?") follows the influence
direction. **Dependency discovery** ("what does X need?") follows the opposite.

## Confidence

| Level | Meaning |
|---|---|
| `confirmed` | A parser matched a concrete artefact (a SQL statement, a scheduler entry) |
| `high` | Strong structural evidence (a recognised API call, a file IO call) |
| `medium` | Plausible inference (a config key that looks like a hostname) |
| `low` | Weak signal (an environment variable name, a library import) |
| `manual` | A human wrote it down |

Every relationship carries a confidence level **and** at least one evidence
row. Nothing in the graph is asserted without provenance.

Users can confirm or reject a discovered relationship. Rejected relationships
are excluded from the default graph but never deleted — the reasoning is worth
keeping.

## Evidence

```text
Evidence
├── subject        entity or relationship
├── kind           source_line | sql_statement | connection_string |
│                  url | file_path | scheduler_entry | cron_expression |
│                  config_key | import | manual_note | inferred
├── source_path    the artefact
├── line_start     where in it
├── snippet        redacted excerpt
├── parser         which scanner produced it
└── confidence     how sure
```

The evidence panel in the UI is the product's trust surface: if Atlas claims
`nightly-export.ps1 READS_FROM Student.Person`, it shows you line 87 and the
query text.

## Identity and reconciliation

Every entity has a `fingerprint` — a natural key of
`entity_type | normalised identity | path tail`. Path-shaped identities are
compared by their last three segments so the same file discovered through
different notations unifies into one entity.

Server-scoped identities (from a per-server bundle, see ADR-006) fold the
execution host into the fingerprint: `APP01::/opt/sync.py` and
`APP02::/opt/sync.py` stay distinct.

This is what makes rescans safe: a rescan updates what changed, leaves manual
edits alone, and never duplicates. Manual fields (`manual_fields_json`) are
never clobbered, and discoveries a scan confirms are gone are retired
(`is_active = false`) rather than deleted. See
`docs/adr/003-entity-identity-and-rescans.md` and
`docs/adr/005-scan-provenance-and-retirement.md`.

## Workspaces

A workspace is an isolated scope — "Student Systems", "Finance Integrations",
"Whole Organisation". It owns its own entities, relationships, evidence,
scans, risk findings and manual edits.

## Risk findings

Heuristic, explainable, and never a black-box score. Each finding names its
rule, states why it fired in plain language, and lists the artefacts it
pointed at.

Rules cover: hard-coded credentials, hard-coded IPs, UNC paths, deprecated
hostnames, missing owners, undiscovered dependencies, dependency
concentration, unusual ports, and scheduled jobs pointing at missing scripts.
