---
name: setup
description: "Create, align, or update a runnable technical project baseline, including toolchains, adding/removing direct packages, dependency version changes, data infrastructure, commands, CI, ProjectContext, and initial repository delivery. Use for project setup and later foundation changes; exclude product planning, feature implementation, review-only work, application deployment or package/artifact publication, and work owned by a narrower installed platform setup skill."
---

# Establish a Technical Project Baseline

Own the technical foundation from settled product needs through a reproducible, runnable baseline. `ProjectContext.md` is one required interface, not the delivery by itself.

## Establish the operation

Read the shared [delivery policy](../../references/delivery-policy.md) and [operation modes](references/operation.md), then select Create, Align, or Update. Use confirmed project/Git inputs, choose unspecified reversible details with stable compatible releases and official generators, and ask only about a project-shaping fact or new authority. Prefer a narrower installed platform setup capability when it fits; this skill maintains no platform profiles.

## Build and verify the baseline

Read [technical baseline](references/technical-baseline.md). Configure each confirmed layer and prove its foundation smoke without inventing business behavior. Setup owns direct dependency changes, dependency resolution, package-manager configuration, dependency-related manifest fields and resulting lockfiles; other manifest fields follow their actual meaning. Feature implementation waits for a separate dependency Setup delivery. Update-caused compatibility code stays in that Setup transaction.

Fill the `assets/` templates only with verified facts. Preserve authored files. Keep stable operations in `ProjectContext.md`, leaf versions in manifests/lockfiles, and progress in Task/PR records.

## Deliver the setup

Read [delivery](references/delivery.md). New GitHub delivery uses a complete, independently reviewed initial commit and its one authorized default-branch push. Later Setup work uses a ready PR with author Monitor and one independent reviewer through merge or handoff.

Run declared install, lint, test, build, CI-equivalent and foundation-smoke entry points. Report selections, reference adoption, exact evidence, Git/CI state and limits. Generator success, caches, unrun checks or a document-only shell never establish completion.

Routing and output regression fixtures live in `evals/` for skill maintenance; reports record their evidence limits and are not execution authority.
