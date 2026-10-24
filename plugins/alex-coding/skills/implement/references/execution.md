# Implementation Evidence

Read the narrow source closure from the contract bound to this delivery and relevant current code. Expand only to resolve an actual missing fact, affected caller or contradiction within this delivery. Completed contracts from earlier deliveries are optional history and do not supply acceptance criteria. Return changes to the active delivery's product meaning to Plan rather than writing a test that invents a requirement.

## Record proportionate acceptance before code

Use the current delivery's accepted contract as the authority for that delivery's correctness. Derive concrete setup/action/expected-result cases without reinterpreting the source document or independently inventing requirements. Each case keeps the original clause ID and a stable suffix, for example `MOVE-02/T03`. Store the checklist in the project's existing task/acceptance location, or another simple agreed repository location; do not require a new documentation system.

A clause may need multiple cases, and a case may require evidence from more than one layer. Use representative observable failures instead of a combinatorial test matrix. Preserve the contract meaning and exclusions; return actual gaps or contradictions to Plan rather than changing acceptance.

For direct work without a Delivery Contract, keep one short checklist in the existing task or PR: accepted request and clarifications, observable outcome, exact existing/new test name or other verification method, and observed result/revision. Number checklist items when useful, but do not require synthetic clause IDs, a separate document, or test renames solely for tracing. Reuse this record for the PR and reviewer input; export a local copy when the runner needs a file instead of maintaining another acceptance narrative. A direct request never bypasses an unfinished Plan-owned delivery.

Choose verification from the accepted outcome and concrete failure risk, not from what is easiest to unit-test. Before implementation, mark each case's verification method and identify integration or human/UI evidence that remains outside unit scope. Do not call storage/file-backed integration checks unit evidence. Do not add UI automation or CI UI jobs as part of this workflow unless separately requested. Deferring UI automation does not mark a UI requirement satisfied; report user-owned or unresolved acceptance honestly.

## Decide whether a new test earns its cost

A PR may add no tests. Before adding one, identify the plausible defect, its user/caller consequence, and why existing coverage, compiler checks or proportionate inspection do not adequately protect it. Keep this rationale brief in the existing acceptance record; do not create a per-test ledger. New/public APIs, changed lines, clause IDs, coverage percentages and test counts are not reasons by themselves.

Reuse or strengthen an existing scenario first. Add the smallest independent behavior check for an uncovered concrete regression or meaningful risk, such as nontrivial decisions, transformations, state transitions, failure recovery, persistence, security or concurrency. Do not waive validation at trust boundaries or protection against data loss merely to reduce tests. Simple property assignments, constant/default restatements, transparent forwarding and unchanged code moves normally need no new runtime tests; compiler checks and inspection can suffice. Exercise multiple types or inputs only when they expose distinct failure mechanisms, not merely because the API accepts them. Assert observable outcomes rather than copying the implementation's steps or deriving expectations through the same logic.

## Test and implement

For a justified new unit test, prefer writing meaningful scenario assertions and recording their natural failure before the smallest implementation change, then return Green. Existing correct behavior can begin Green. Never retroactively manufacture Red if implementation already exists; report the observed starting state honestly. Avoid duplicate tests merely to create another numbered artifact.

Include relevant normal, boundary and exceptional business scenarios. Set up failures through test inputs, fixtures or a controlled dependency, such as a storage double that returns a save error, then assert the required response and preserved state. An expected business failure should make the test pass when the implementation handles it correctly. Do not use unconditional failing assertions or change expected results to force failure.

Do not perform mutation testing: do not temporarily break correct production code or alter assertions/expectations to see whether an existing test detects the change. A plan saying a test must detect a particular defect calls for meaningful scenario assertions, not a destructive experiment. If a concrete coverage gap appears, add or strengthen the corresponding business-scenario test. Do not turn every test into another task to validate the test itself.

Stop when the accepted scenarios have adequate evidence and required project checks pass. Add further verification only for a specific unmet criterion, observed regression or new evidence; do not extend delivery through speculative test-validation cycles.

For Contract work, include the acceptance case ID in the test name or framework display name so failures can be traced back to the checklist and contract. Normalize the ID for language identifiers when necessary, preserving a deterministic recoverable form, such as `MOVE_02_T03`. Do not add prohibited source comments. Existing adequate tests can receive the ID in their name/display metadata and be mapped instead of copied. For direct work, mapping the outcome to the existing test identifier is sufficient.

Maintain the mapping from contract clause to acceptance case to the chosen verification method and observed result; include exact test identifiers where tests supply that evidence. A matching title is not proof: assertions must establish the case's expected outcome. Run declared project checks and report remaining non-unit evidence separately. The implementation reviewer checks both coverage of in-scope clauses and whether the actual assertions/code support the numbered cases. Worker verification makes no new product decisions.

Use declared lint/test/build entry points, respecting directory allowlists and platform-tool authorization. Passing exact-head evidence does not need repetition solely because another Agent reads it; rerun when changed code, missing or contradictory evidence, project policy or an observed defect warrants it.

Temporary local shared-package overrides are development tools, not portable delivery artifacts. Respect project policy for dependency publication and pinning. Do not infer that repository-owned local packages are invalid.

Direct dependency additions, removals, replacements and version changes, plus dependency resolution, package-manager configuration, dependency-related manifest fields and resulting lockfile changes, belong to Setup. Other manifest fields follow their actual product or technical meaning. When an accepted feature requires a foundation change, preserve the feature work, complete and merge a separate Setup delivery, then resume implementation on the new baseline. An already-merged dependency baseline can be consumed normally; feature implementation does not repeat its Setup checks without contrary evidence.

A PR report states what changed, why, which checks actually ran and their limits. Test totals describe execution scope, not test value or acceptance completeness. Never promote intended checks, cached historical reports or contract assertions into a current passing result.
