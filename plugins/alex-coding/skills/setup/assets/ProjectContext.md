# <Project Name> Project Context

This file is the stable project-specific entry point for planning, setup, implementation, review, and investigation. It records verified technical facts and routes readers to their owning sources; delivery progress belongs in Task and PR records.

## Purpose and project form

- Purpose: <concise product purpose>
- Form and runtime environment: <Web app, service, CLI, library, native App, or another verified form>
- Primary languages and runtimes: <values and supported version baseline>
- Package manager and dependency source of truth: <values>

## Technical foundation

- Frontend or presentation: <value or not applicable>
- Backend or service: <value or not applicable>
- Database, storage, and migration owner: <value or not applicable>
- Generator and generated-file source of truth: <value or not applicable>
- Default local service address/port: <value or not applicable>
- Task preview/debug address or port rule: <value or not applicable>
- Debugging workflow and commands: <how to reproduce, inspect logs/state, reset disposable data, and avoid disrupting a persistent service>

## Structure and ownership

Describe the important source, test, configuration, generated, data, and documentation paths. State the architectural ownership and dependency boundaries that later work must preserve.

## Install, run, and verify

List the exact project-owned commands for dependency installation, local run/preview, formatting/linting, tests, build, database initialization/migration, and the technical foundation smoke. Distinguish local, CI, device, deployment, and human acceptance evidence.

## Data, secrets, and external services

Record local data paths, disposable test-data rules, migration/backup boundaries, environment-file conventions, required secret names without values, and any authorized external service or trust boundary.

## Authoritative sources

Link current engineering documentation, accepted product/design sources, delivery records, and any continuing reference-project or shared-tool dependency. Distinguish current authority from historical evidence and one-time setup inputs.

## Acceptance and delivery

Record which outcomes require human acceptance, the established PR/review path, the initial-repository exception when applicable, and any device, deployment, publication, external-service, or real-data authorization boundary.

## Exceptions and open questions

Record durable project-specific exceptions and unresolved technical decisions that affect current work. Do not turn this section into a delivery backlog or implementation diary.

## Setup and maintenance

All direct dependency, runtime, framework, database, package-manager, generator, CI, port, or development-flow changes are Setup work. Update this file in the same Setup delivery when a recorded stable fact changes. Do not turn it into an implementation diary or copy exact leaf dependency versions from the manifest/lockfile.
