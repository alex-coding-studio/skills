---
name: implement
description: "Implement and deliver accepted repository changes, using the current Delivery Contract when present or the user request directly. Exclude planning, setup and review-only work."
---

# Implement Accepted Repository Work

Own implementation, verification, the code PR and author feedback. Read [project context](../../references/project-context.md) and [delivery policy](../../references/delivery-policy.md); reuse unchanged guidance within the same task and load only the runtime in use.

## Acceptance and focused entry

For a Plan handoff, verify the planning PR is merged, the supplied full SHA is its actual merge result, and the contract at that revision identifies this delivery. Read its relevant sources, not every historical contract. Return material changes to this active delivery's product meaning to Plan. Completed contracts stay historical and unchanged.

Without a Contract, use the user's accepted request and direct clarifications. Do not repeat acceptance, require a planning PR, or bypass an unfinished Plan-owned delivery. Preserve project rules for protected documents and human approvals; ask only about ambiguity that prevents implementation or verification.

For a diagnosed Issue, batch the Issue, named code, relevant tests and verification entry points. Verify the diagnosis and affected callers; suggestions are evidence, not instructions. Expand only for missing facts, changed locations, dependencies or contradictions. Do not repeat repository discovery when current context is adequate.

## Implement and deliver

1. Resolve default/current branches and checkout ownership. For a new delivery, use the [disposable worktree lifecycle](../../references/worktree-lifecycle.md): synchronize the primary default checkout, then create a new task worktree with the bundled script. Resume an existing delivery in its existing worktree. Keep development off the primary checkout.
2. Read [execution.md](references/execution.md). Record acceptance before code in one existing task/PR location. Contract cases retain clause IDs; direct work maps observable outcomes to test identifiers without renaming adequate tests solely for IDs. Reuse this record for review rather than maintaining duplicate narratives.
3. Use scenario-driven TDD for unit-observable new behavior or concrete regressions: natural Red, implementation, Green. Reuse adequate coverage. Never mutate correct code/assertions to manufacture Red. Documentation, prompts and mechanical changes use applicable validation without invented tests. Follow relevant specialist guidance and accepted scope.
4. Run unchanged project gates and record exact-revision results and limits. Do not repeat adequate checks solely because another Agent reads them. Human/UI acceptance remains separate; obtain it before PR creation when the project requires it. Builds and screenshots do not supply human acceptance.
5. Open a ready PR with the configured author identity; Draft only when requested or required. The bundled [delivery helper](references/delivery.md), `scripts/delivery.py`, composes creation, Monitor registration and independent Review startup with compact receipts. Reuse an assigned reviewer and runtime transport; report unavailable execution as inactive, never self-approve. Select reviewer complexity by [policy](../review/references/runtime.md#model-and-effort-policy), not diff size.
6. Handle current feedback under existing authorization. Create required follow-up Issues for independent non-blockers. A push or queue receipt is not resolution. Keep Monitor and Review attached to this exact PR; waiting invokes no model. Respect cumulative review limits and human-owned gates. User-authorized fresh review uses Review's `continue --decision-file`, independently of old publication.
7. Under existing merge authorization, recheck current head-bound approval, unchanged gates, blocking feedback and mergeability, then merge and invoke Monitor's protected completion. The helper composes these steps without bypassing protections. For disposable targets, synchronization and force-removal are independent script operations; local residue never blocks disposal. Preserve unproven identities and closed-unmerged deliveries.

Continue through acceptance and authorized delivery; pause only for a real blocker or user-owned decision. Report outcome, verification, PR and remaining limits. A merge does not authorize milestone changes or a retrospective. Use bundled Monitor by default unless opted out; its runtime owns queue/acknowledgement behavior.

For requested cost comparisons, use [usage.md](references/usage.md) and `scripts/usage_report.py`; ordinary deliveries need no telemetry artifacts or live comparisons. Routing fixtures are in `evals/` for skill maintenance.
