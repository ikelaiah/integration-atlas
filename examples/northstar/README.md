# Northstar example artefacts

A small but realistic slice of the Northstar Education Group estate, in the
form it actually exists on disk: SQL extracts, PowerShell jobs, Python
integrations, config files, a Windows Task Scheduler export and a cron entry.

Use it to see what Integration Atlas discovers:

```bash
atlas scan ./examples/northstar
atlas serve
```

Secrets in these files are **intentionally fake** and are redacted on the way
into the database anyway — check `settings.ini` to see the redaction layer at
work.
