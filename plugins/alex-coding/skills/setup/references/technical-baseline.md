# Technical Baseline Contract

## Required baseline

Configure the confirmed runtime, package manager, application or package generator, frontend/backend/data layers, direct dependencies, source ownership, environment inputs, local commands, CI, and development/preview behavior. Use official tools instead of recreating ecosystem scaffolding.

Each declared layer needs its natural foundation smoke without invented product behavior:

- a Web page opens;
- a service starts and, when useful, answers a non-business health check;
- a database connects and applies its baseline migration;
- a CLI shows help or performs a harmless command;
- a library compiles and runs a minimal test;
- a native project generates, opens, builds, and launches through its declared entry points.

Generator success alone is not evidence. Verify from a clean dependency state when practical, and distinguish local checks from CI, device, deployment, and human-experience evidence.

## Dependency ownership

Setup owns runtimes, frameworks, databases, package managers, generators, CI, commands, ports, debug flows and their versioned engineering documentation, plus standalone dependency/toolchain updates. A feature, fix or removal PR may add, remove, replace or update the direct dependencies it needs with matching manifest and lockfile changes in the same PR. Disclose each dependency change in the PR description, update affected versioned engineering sources in that delivery, and follow the declared provider for authorized durable knowledge updates at the applicable delivery point. Other manifest fields follow their actual product or technical meaning.

An update transaction may contain only changes directly caused by the update: API migrations, compiler fixes, configuration formats, generated output, compatibility adapters, data/ORM migration formats, tests that preserve the same behavior, and removal of obsolete compatibility code. New business behavior and unrelated cleanup remain outside Setup.

Update affected versioned technical sources in the same Setup delivery when a recorded foundation fact changes. Exact dependency versions remain in manifests and lockfiles. Follow the target’s declared provider for authorized durable knowledge updates at the applicable delivery point.

## Context and instruction assets

Every project formally created or aligned by Setup has:

- root `AGENTS.md` with applicable project rules and direct pointers to declared sources;
- a runtime adapter only when the target requires one to load that entry. For new projects in a workspace with a shared AGENTS-only entry, use that workspace’s format and verified provider identity;
- `README.md` with the human entry point;
- a detailed engineering document such as `docs/PROJECT.md` when commands and operations exceed the concise context.

Use the templates in `../assets/` as a structure, not as accepted facts. Replace every placeholder, omit inapplicable sections, preserve authored content, and never create parallel authorities.

Keep verified project form, runtime, framework and data choices, source ownership, generator, commands, ports, debugging flow, and data, migration and secret boundaries in the entry or its versioned engineering pointers. Keep durable decisions and project state in the target’s declared provider and progress in task or PR records.

## Data and security changes

A foundation change that requires data migration owns the migration plan, rehearsal, verification, and rollback boundary. Operating on real data needs explicit authorization and a recoverable backup. Do not infer business-field meaning or discard data to make a new stack run.

Do not run destructive audit fixes automatically. Assess whether a finding affects the actual runtime path; apply compatible fixes through Setup, and report major or behavior-changing remediation for a decision.
