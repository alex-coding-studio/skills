# Setup Operation Modes

## Required project facts

Before writing, resolve from the conversation and current repository evidence:

- project name, purpose, and target form such as Web app, service, CLI, library, or native App;
- primary runtime environment and any user-fixed technology/version constraints;
- local destination and whether it is empty, an existing project, or an assigned worktree;
- Git choice and, for GitHub delivery, owner, repository name, visibility, explicit one-time default-branch exception, and public-repository license;
- optional reference project and any external service, account, paid resource, data-export, or deployment requirement.

Do not require a complete product specification. If the purpose and target form are clear, choose unspecified technical details using stable compatibility, official guidance, the runtime environment, and relevant reference evidence. Summarize the choices after execution. Pre-confirm only material external state, machine-wide changes, irreversible migrations, product behavior, or supplier lock-in.

## Create

Use an empty destination. Reject or reclassify a non-empty destination before a generator can overwrite it. Prefer the selected ecosystem's official generator and project-local dependency management. Configure all confirmed layers, context files, verification entry points, CI, and foundation smoke before GitHub publication.

## Align

Inspect the existing Git state, instructions, `ProjectContext.md`, detailed engineering docs, manifests, lockfiles, scripts, CI, and runtime entry points. Preserve dirty or authored work. Do not rerun a full generator blindly or overwrite an authored context. Establish only the missing or explicitly accepted baseline and deliver it through a Setup PR.

## Update

Investigate the named foundation change, affected manifests/configuration, direct callers, migrations, tests, and declared gates. Prefer the smallest stable compatible change. Do not upgrade unrelated packages or refactor unrelated code. If preserving existing behavior requires a product decision, stop and ask before changing that behavior.

Project-wide runtime, framework, database, ORM, package-manager, UI-foundation, build, test, lint, port, or development-flow changes belong here. Do not upgrade merely because a newer release exists; act on an explicit request, a confirmed requirement, or a blocking compatibility/security condition.

## Reference projects

When the user says to reference another project, read its root `ProjectContext.md` completely when present, then follow only the relevant pointers into engineering docs, manifests, lockfiles, scripts, and CI. If it has no ProjectContext, fall back to its project instructions, README, engineering docs, manifests and declared commands; report the missing context once and continue when those sources establish the technical baseline. Do not create or modify context in the reference project as a side effect. Reuse applicable technical choices, not product or business implementation.

Record in the delivery summary what was adopted, adjusted, and rejected. Never inherit project/repository identity, secrets, real data, business schemas, screens, workflows, progress records, machine paths, or external resources without separate evidence and authorization. Record the reference in the new ProjectContext only when an ongoing technical dependency remains.

## Permission boundary

Project-local installs are ordinary Setup work. Ask before Homebrew/system package installation, global runtime or package-manager changes, background services, shell-profile edits, certificates, device permissions, or changes that can affect other projects. Create secret names and `.env.example`, never copy values from a reference project or commit credentials.
