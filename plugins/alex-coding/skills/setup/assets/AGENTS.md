# <Project Name> Agent Instructions

Read root `ProjectContext.md` before planning, setup, implementation, review, or investigation. Follow its relevant source pointers, architecture boundaries, commands, ports, data rules, and evidence requirements. Refresh it when the current task changes a recorded technical baseline.

Preserve authored project context, unrelated changes, and the user's accepted scope. Do not invent product decisions, copy business behavior from a reference project, or treat delivery history as current authority.

Setup owns runtimes, frameworks, databases, package managers, generators, CI, commands, ports, debug flows and ProjectContext, plus standalone dependency/toolchain updates. Explicit package addition, removal or update requests may use Setup. A feature, fix or removal PR (Implement) may add, remove, replace or update the direct dependencies it needs, with matching manifest and lockfile changes in the same PR. List each dependency change in the PR description and update ProjectContext when it names that dependency. Reviewers must not require a separate Setup PR or treat these dependency changes as a blocker. Other manifest fields follow their actual product or technical meaning.

Use the project's declared install, lint, test, build, preview, migration, and foundation-smoke entry points. Passing one layer does not establish another. Follow the applicable shared Git, GitHub identity, PR, review, UI acceptance, device, deployment, and external-service rules.
