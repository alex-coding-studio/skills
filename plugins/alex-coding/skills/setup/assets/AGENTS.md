# <Project Name> Agent Instructions

Read root `ProjectContext.md` before planning, setup, implementation, review, or investigation. Follow its relevant source pointers, architecture boundaries, commands, ports, data rules, and evidence requirements. Refresh it when the current task changes a recorded technical baseline.

Preserve authored project context, unrelated changes, and the user's accepted scope. Do not invent product decisions, copy business behavior from a reference project, or treat delivery history as current authority.

All direct dependency additions, removals, replacements and version changes, plus dependency resolution, package-manager configuration, dependency-related manifest fields and resulting lockfile changes, belong to the project's Setup workflow. Other manifest fields follow their actual product or technical meaning. Feature implementation must not hide foundation changes inside a business delivery.

Use the project's declared install, lint, test, build, preview, migration, and foundation-smoke entry points. Passing one layer does not establish another. Follow the applicable shared Git, GitHub identity, PR, review, UI acceptance, device, deployment, and external-service rules.
