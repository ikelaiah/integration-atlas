# ADR 004: Secret redaction at every persistence boundary

**Status:** Accepted · 2026-10

## Context

Redaction was applied to snippets, descriptions and locations, but two paths
still let a credential reach the database:

1. `qualified_name` was persisted verbatim. A config URL of the form
   `scheme://user:password@host` therefore kept the password in the entity's
   identity, and exports reprinted it.
2. `meta_json` was persisted verbatim. Task Scheduler arguments such as
   `--password=…` survived inside structured metadata.

There was also a detection bug: `_is_allowlisted` scanned an 80-character
window around a match, so an allowlisted key on a nearby line
(`token_type=Bearer`) suppressed a real secret on the next line
(`password=…`).

## Decision

* **Redact every field that can reach a row.** In addition to snippet,
  description and location, the normaliser now redacts `name`,
  `qualified_name`, `owner`, `technology` and every string inside
  `meta_json` (recursively). The API write paths (create/update entity,
  create/update relationship, add evidence) apply the same redaction, and the
  exporters redact defensively even though persisted rows are already clean.
* **Key-scoped allowlist.** The allowlist is consulted only for the key that
  owns the matched assignment. Keyless patterns (JWT, AWS keys, PEM blocks,
  embedded URL/userinfo credentials) are never suppressed.
* **Quoted keys and scheme-less userinfo.** Credential detection accepts
  JSON-style quoted keys (`"password": "…"`) and scheme-less `user:pass@host`,
  so supported config formats all behave the same.
* **Sanitised identities stay referenceable.** The normaliser redacts a
  reference before resolving it and computes fingerprints from the sanitised
  identity, so the same artefact maps to the same entity on every scan while
  secrets never enter the fingerprint.

## Consequences

* Nothing sensitive can survive in persisted fields, evidence, metadata or
  exports; leak tests assert a synthetic secret is absent from every string
  column.
* A secret that appears in an identity is masked deterministically, so
  rescans still reconcile instead of duplicating.
* The detector is more willing to redact (quoted keys, scheme-less userinfo),
  consistent with "false positives are cheap, false negatives are not".
