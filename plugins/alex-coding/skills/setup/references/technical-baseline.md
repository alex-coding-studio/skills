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

Every direct dependency addition, removal, replacement or version change is Setup work, including dependency resolution, package-manager configuration, dependency-related manifest fields, and resulting lockfile changes. Manifest fields that describe product entry points, application metadata or feature behavior remain with their semantic owner. A feature that needs a new dependency completes and merges a separate Setup delivery before feature implementation resumes.

An update transaction may contain only changes directly caused by the update: API migrations, compiler fixes, configuration formats, generated output, compatibility adapters, data/ORM migration formats, tests that preserve the same behavior, and removal of obsolete compatibility code. New business behavior and unrelated cleanup remain outside Setup.

Update `ProjectContext.md` in the same Setup delivery when the stable runtime, framework, data layer, package manager, generator, commands, ports, preview/debug flow, or another recorded foundation fact changes. Exact leaf versions remain in manifests and lockfiles.

## Context and instruction assets

Every project formally created or aligned by Setup has:

- root `ProjectContext.md` with verified stable project facts;
- root `AGENTS.md` that makes the context discoverable and preserves Setup ownership of dependencies;
- a compatible root Agent adapter such as `CLAUDE.md` when the project uses that runtime;
- `README.md` with the human entry point;
- a detailed engineering document such as `docs/PROJECT.md` when commands and operations exceed the concise context.

Use the templates in `../assets/` as a structure, not as accepted facts. Replace every placeholder, omit inapplicable sections, preserve authored content, and never create parallel authorities.

ProjectContext directly records the project form, runtimes, package manager, major framework/data choices, source topology, generator/source-of-truth, install/run/test/build commands, default service and preview ports, debugging flow, data/migration/secret boundaries, authoritative sources, and durable exceptions. It is not a progress log.

## Data and security changes

A foundation change that requires data migration owns the migration plan, rehearsal, verification, and rollback boundary. Operating on real data needs explicit authorization and a recoverable backup. Do not infer business-field meaning or discard data to make a new stack run.

Do not run destructive audit fixes automatically. Assess whether a finding affects the actual runtime path; apply compatible fixes through Setup, and report major or behavior-changing remediation for a decision.
