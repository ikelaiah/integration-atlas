# Follow a change through the Northstar estate

Northstar Education Group is a fictional estate included with Atlas. This walkthrough follows a student identifier from its source table to the systems that consume the exported data.

## Start Atlas

From a clean checkout, follow the [Quick start](../README.md#quick-start) to install the CLI and build the web interface, then run:

```bash
atlas demo
atlas serve
```

Open the local URL printed by `atlas serve`. The demo data stays in your local Atlas database.

## Trace StudentID

In the Atlas page, search for `StudentID`, open the matching column, and choose **Impact analysis**. Atlas highlights the downstream path and reports 39 affected entities across 6 integrations in the Northstar demo.

```text
LegacySIS.Student.Person.StudentID
  → student_extract.sql
  → export_students.ps1
  → students.csv
      ├─ identity_sync.py          → IdentityHub
      ├─ nightly_sync.py           → EnrolmentPortal
      └─ learningcloud_export.ps1  → LearningCloud
```

The shared `students.csv` is the important junction: three separate integrations depend on the same export. A change to the source column can therefore affect more than the first script in the chain.

## Check the evidence

Select a relationship in the graph or open the entity's **Evidence** tab. Atlas shows the source file, line, redacted snippet, parser, and confidence behind each discovery. Follow the evidence back to the sample files in the [Northstar example estate](https://github.com/ikelaiah/integration-atlas/tree/main/examples/northstar).

Atlas performs static analysis: it reads supported artefacts and does not run them. The Northstar estate is synthetic; scanning your own estate remains local to the machine running Atlas.
