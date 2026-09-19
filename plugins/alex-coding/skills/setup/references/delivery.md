# Setup Delivery

## Local-only setup

Complete the verified baseline in the user-selected location. Do not create a remote, publish a package, deploy a service, or provision an external resource unless that action was explicitly included.

## New GitHub repository

Before generation, resolve once whether Git is wanted and, for GitHub delivery, the local path, owner, repository name, visibility, and public license. That confirmed delivery mode authorizes repository creation and the initial push after the complete local baseline passes.

The ready-to-deliver initial baseline includes the generated technical shell, manifests and lockfiles, source/configuration, `.gitignore`, README, ProjectContext, Agent instructions, detailed engineering docs, declared checks, CI, and foundation smoke. Exclude caches, build products, secrets, local databases, private planning stores, and unrelated reference-project content.

Commit the full local baseline, then obtain an independent read-only review of that exact commit before creating/pushing the remote. This is not the bundled PR-only Review workflow. Start an isolated reviewer with:

- the exact local commit SHA and empty-tree-to-commit patch;
- the accepted Setup scope and selected technical baseline;
- the ProjectContext, manifest/lockfile and generated-source ownership;
- install, lint, test, build, CI-equivalent and foundation-smoke evidence;
- the initial-delivery checklist and any external/system/data limits.

The reviewer returns an exact-SHA `approved`, `changes-requested`, or `needs-user-attention` result with evidence. The author fixes blockers in a new commit and obtains a fresh review of that new SHA. If supported independent local execution is unavailable, report the inactive gate and stop before remote creation/publication; do not substitute author self-review or claim that the later PR-only reviewer covered it. The confirmed initial delivery is the one direct default-branch exception; do not split it into an empty default baseline and a shell PR.

After push, follow the first CI run. Local gates do not prove the remote job. If CI exposes a problem, preserve the initial commit and fix it through a normal Setup PR; never force-push or continue direct default-branch updates.

## Existing repositories and later changes

Use one task worktree and ready PR for each later Setup delivery. Keep dependency/version changes separate from business feature PRs. The Setup PR carries required compatibility changes, migrations, tests, documentation, ProjectContext updates, verification, and rollback limits as one transaction.

After opening the PR, register `alex-coding:monitor` with the exact task-owned checkout and start or reuse one independent `alex-coding:review` reviewer bound to that PR. Use the existing [delivery helper](../../implement/references/delivery.md) when its runtime path applies; otherwise follow the same project-configured identity, monitoring, review, feedback, merge and protected-cleanup rules directly. Approval belongs to the independent reviewer and current head. Setup owns author feedback, required follow-up work, merge under existing authorization, and terminal cleanup.

Create CI by default when a GitHub-delivered project has declared gates. Do not claim or configure branch protection, required checks, publication, deployment, container hosting, or paid/external services without their own authority. CI availability and enforcement are separate facts.

Use the project's configured Git/GitHub identities and review rules. A Setup request does not bypass repository policy except for the expressly confirmed new-repository initial commit described above.

## Completion report

Report:

- operation mode and destination;
- selected runtimes, frameworks, data layer, dependencies, and exact relevant versions;
- official generator and reference-project adoption/adjustments;
- ProjectContext and command/port/debug boundaries established or changed;
- install, lint, test, build, CI-equivalent, and foundation-smoke evidence;
- commit/PR/remote/CI state;
- security, migration, external-service, review, deployment, publication, or machine-environment limits.
