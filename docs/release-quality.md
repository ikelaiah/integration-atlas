# Release quality bar

Integration Atlas should be easy and pleasant to read, use, learn from, and
maintain. Its diagrams and results should be clear enough that another
developer can understand and trust them.

This is the quality bar for v0.1.0 and future releases. It applies to the whole
experience, not only feature count.

## Read

- A first-time contributor can find the main concepts and follow a feature
  from scanner input through persisted evidence and the UI.
- Names, boundaries, and examples match the domain model and each other.
- Architecture decisions explain the reason for important constraints.

## Use

- A clean checkout can install dependencies, load the demo, and open the app
  using the documented commands.
- Errors say what failed and how to recover; a missing frontend or empty estate
  has a clear next step.
- Scanning remains local and read-only with respect to discovered artefacts.

## Learn

- A discovery shows its source, evidence, confidence, and relationship meaning.
- The demo demonstrates a realistic integration story and can be reset safely.
- The server-bundle guide makes it clear how to attribute jobs to execution
  hosts without guessing from task contents.

## Maintain

- Backend tests and lint, frontend type checking and build, and Docker build run
  automatically on proposed changes.
- Database upgrades preserve existing data and can be repeated safely.
- The README, install path, security policy, and release notes describe the
  behavior users receive.

## Present

- Graph labels, arrows, and evidence remain legible at realistic estate sizes.
- Filters and impact views help explain the graph without hiding its meaning.
- Shared results and exports keep the source and confidence needed to assess
  them.

## Publish the documentation site

The `DocSprout Pages` workflow builds the README and selected `docs/` pages and
publishes them to GitHub Pages. For the first deployment, set the repository's
Pages source to **GitHub Actions** in **Settings → Pages → Build and deployment**.
After enabling Pages, start the workflow from **Actions → DocSprout Pages →
Run workflow** on the default branch. Later pushes to the default branch publish
automatically. The site is available at
https://ikelaiah.github.io/integration-atlas/.

## v0.1.0 release checks

- [ ] CI passes on Python 3.11, 3.12, and 3.13.
- [ ] Frontend type checking and production build pass.
- [ ] Docker image builds and serves the built frontend at `/` and API health at
      `/api/health`.
- [ ] A clean install follows the README exactly and reaches the demo graph.
- [ ] An existing database upgrades without losing entities, evidence, or
      manual edits.
- [ ] Compose exposes the unauthenticated local app only on loopback by default.
- [ ] Secret-redaction regression tests pass for scans, API writes, and exports.
- [ ] Release notes state the supported install path, upgrade behavior, known
      limits, and how to report vulnerabilities.
- [ ] Tag `v0.1.0` points to the commit that passed these checks.
