# ADR 010: Reserve the demo workspace for Northstar data

## Context

Before v0.6.0 the web app seeded Northstar into an empty database and had no
way to create a workspace. A scan from **Scans** therefore wrote into the demo
workspace, and the review-workflow guide documented that flow. Resetting the
demo deleted every entity and relationship in that workspace, including scan
discoveries, while their scan history remained. People could not tell sample
data from their own, and a reset could silently delete their work.

## Decision

The demo workspace holds only Northstar data. The API and CLI refuse to
preview or apply a scan into a workspace marked `is_demo` (HTTP 409), and
refuse to create a regular workspace whose name maps to the demo's slug. A
scan preview may name a workspace that does not exist yet; it is created
inside the preview's rolled-back savepoint, so only applying a scan creates it.

A reset restores the Northstar bundle. Edits to demo entities and review
decisions on demo relationships are reverted, because that is what a reset of
sample data means. Data from anywhere else is never deleted. Atlas identifies
it by scan history in the workspace, or by entity and relationship
fingerprints that are not in the Northstar bundle. When such data exists, the
reset first turns the current demo workspace into a regular workspace named
`Northstar Education Group (kept YYYY-MM-DD)`, with all its rows and scans,
then creates a fresh demo workspace. `GET /api/demo` reports these counts so
the UI can say what will happen before anything changes.

## Consequences

Older databases need no migration: the rules read existing columns. A demo
that already mixes in scan results keeps working until its next reset, which
separates the data instead of deleting it. Guides that scanned
`examples/northstar` into the demo now scan it into a workspace of the
reader's own. The demo is located by `is_demo`, not by slug, so a regular
workspace that already uses the demo slug is never reseeded.
