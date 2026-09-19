# Output Blind A/B Review Pack

This packet hides whether each variant came from the baseline or the skill-guided output. Use the separate answer key only after review.

- Pairs: `4`
- Seed: `yao-output-eval-blind-v1`
- Answer key separate: `True`

## Case: create-runnable-baseline

Prompt: Create a new private Node web project after the user described its purpose but left the stack versions unspecified.

Rubric:
- `runnable` (1.0): Creates and verifies a runnable baseline rather than documentation alone.
- `context` (1.0): Creates the durable project interfaces.
- `delivery` (1.0): Uses the authorized complete initial delivery path.
- `boundary` (1.0): Does not invent product behavior.

### Variant A

Create a README and ProjectContext, initialize Git, and tell the user to add the application later.

### Variant B

Choose a stable compatible Node and framework baseline, use the official generator, pin direct dependencies with a lockfile, configure the confirmed frontend/backend/data layers, create AGENTS.md, ProjectContext.md, README.md and detailed engineering commands, add CI, run clean install, lint, tests, build and foundation smoke, obtain independent review of the exact complete initial commit, then create the private repository and push that ready-to-deliver baseline. Report selected versions, evidence, ports, debug flow and limits without adding business features.

## Case: reference-technical-only

Prompt: Set up a new website using Harvis as a reference.

Rubric:
- `reference-evidence` (1.0): Uses ProjectContext as the technical entry point.
- `business-boundary` (1.0): Excludes the reference project's business implementation.

### Variant A

Copy the Harvis repository, rename it, and remove household pages later.

### Variant B

Read Harvis ProjectContext first and follow its engineering pointers into manifests, scripts and CI. Use the selected ecosystem's official generator for a clean project, adopt only applicable runtime, dependency, command, port, preview and data-boundary choices, and list adopted, adjusted and rejected settings. Do not copy Harvis business models, screens, data, repository identity or secrets.

## Case: dependency-separation

Prompt: Implement image upload; the existing project has no image-processing dependency.

Rubric:
- `owner` (1.0): Keeps direct dependency work in Setup.

### Variant A

Pause feature implementation. Create and merge a separate Setup delivery that adds, locks and verifies the direct dependency, runs the project gates and updates ProjectContext only if a recorded stable fact changes. Resume the Implement delivery after the Setup PR merges.

### Variant B

Add the package to the feature branch and implement uploads in one pull request.

## Case: version-update-transaction

Prompt: Upgrade the ORM major version; its API and migration format changed.

Rubric:
- `transaction` (1.0): Carries the full update-caused compatibility closure.
- `data-boundary` (1.0): Does not change product meaning or real data without authority.

### Variant A

Change the version and regenerate the lockfile. Leave compilation errors for the feature team.

### Variant B

Deliver one Setup PR containing the ORM version and lockfile change, every directly required API/configuration/migration compatibility edit, tests that preserve existing behavior, the ProjectContext update, migration rehearsal and rollback boundary, and the complete declared gates. Stop for a decision before changing product semantics or operating on real data.
