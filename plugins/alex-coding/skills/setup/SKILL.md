---
name: setup
description: "Create, align, or update a runnable technical project baseline, including toolchains, standalone direct package additions/removals and dependency version changes, data infrastructure, commands, CI, versioned engineering documentation, and initial repository delivery. Use for project setup and later foundation changes; exclude product planning, feature implementation, review-only work, application deployment or package/artifact publication, and work owned by a narrower installed platform setup skill."
---

# Establish a Technical Project Baseline

Own the technical foundation from settled product needs through a reproducible, runnable baseline.

## Establish the operation

Read the [repository entry and declared context](../../references/project-context.md) and shared [delivery policy](../../references/delivery-policy.md) and [operation modes](references/operation.md), then select Create, Align, or Update. Use confirmed project/Git inputs, choose unspecified reversible details with stable compatible releases and official generators, and ask only about a project-shaping fact or new authority. Prefer a narrower installed platform setup capability when it fits; this skill maintains no platform profiles.

## Build and verify the baseline

Read [technical baseline](references/technical-baseline.md). Configure each confirmed layer and prove its foundation smoke without inventing business behavior. Setup owns runtimes, frameworks, databases, package managers, generators, CI, commands, ports, debug flows and their versioned engineering documentation, plus standalone dependency/toolchain updates. A feature, fix or removal PR may add, remove, replace or update the direct dependencies it needs with matching manifest and lockfile changes in the same PR. Disclose each dependency change in the PR description, update affected versioned engineering sources in that delivery, and follow the declared provider for authorized durable knowledge updates at the applicable delivery point. Update-caused compatibility code stays in the standalone Setup transaction.

Fill the applicable `assets/` templates with verified facts and preserve authored files. Keep stable operations in the repository entry and its technical pointers, exact dependency versions in manifests and lockfiles, and progress in task or PR records. Follow the target’s declared provider for durable knowledge.

## Deliver the setup

Read [delivery](references/delivery.md). New GitHub delivery uses a complete, independently reviewed initial commit and its one authorized default-branch push. Later Setup work uses a ready PR with author Monitor and one independent reviewer through merge or handoff. A version or pin bump in a repository that declares the `pin` review exemption skips the reviewer; see Implement's [declared exemptions](../implement/references/delivery.md#declared-review-exemptions).

Run declared install, lint, test, build, CI-equivalent and foundation-smoke entry points. Report selections, reference adoption, exact evidence, Git/CI state and limits. Generator success, caches, unrun checks or a document-only shell never establish completion.

Routing and output regression fixtures live in `evals/` for skill maintenance; reports record their evidence limits and are not execution authority.
