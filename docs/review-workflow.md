# Review a scan before changing the atlas

Atlas scans folders on the machine where its server runs. You do not install an
agent on source servers. Scanning reads supported files as text; it never runs
the scripts or SQL it finds. GitHub Pages hosts this guide and the Northstar
walkthrough, while the interactive app runs locally with `atlas serve`.

## Try the workflow

1. From a checkout, install Atlas and build the web UI as shown in the
   [quick start](../README.md#quick-start). Run `atlas demo` and `atlas serve`.
2. Open **Scans** in the local app. Enter the absolute path to
   `examples/northstar` and choose **Preview scan**. The preview lists a bounded
   set of entities and relationships that would be added, updated or retired.
   It does not change the workspace or create a scan history entry.
3. Choose **Apply scan**. Atlas reads the files again and saves the resulting
   diff in **Scan history**. If files changed since the preview, the applied
   result can differ. Expand the history row to see what was saved.
4. Open **Review**. Choose a proposed relationship to see its source, target,
   confidence and evidence snippets. Add an optional note and choose
   **Confirm** or **Reject**. A rejected relationship stays in review history
   but is omitted from the normal graph and impact analysis.
5. Open **Atlas**, select an entity and choose **Edit**. Save descriptive
   corrections such as owner and environment. A later rescan retains the
   fields you edited and any relationship verdicts.

The review queue shows active relationships, 50 per page. Scan change lists
show at most 100 entries; their counts include all changes. The change list
contains names and types, not source snippets. Evidence shown in Review is
redacted before it is stored. See [Security](security.md) for scanner limits and
the scan-root allowlist.
