# Implementation Evidence

Read the narrow source closure from the contract bound to this delivery and relevant current code. Expand only to resolve an actual missing fact, affected caller or contradiction within this delivery. Completed contracts from earlier deliveries are optional history and do not supply acceptance criteria. Return changes to the active delivery's product meaning to Plan rather than writing a test that invents a requirement.

## Derive numbered acceptance cases before code

Use the current delivery's accepted contract as the authority for that delivery's correctness. Derive concrete setup/action/expected-result cases without reinterpreting the source document or independently inventing requirements. Each case keeps the original clause ID and a stable suffix, for example `MOVE-02/T03`. Store the checklist in the project's existing task/acceptance location, or another simple agreed repository location; do not require a new documentation system.

A clause may need multiple cases, and a case may require evidence from more than one layer. Use representative observable failures instead of a combinatorial test matrix. Preserve the contract meaning and exclusions; return actual gaps or contradictions to Plan rather than changing acceptance. When the current work has no Delivery Contract, record the user's request, any direct clarifications and their source in the task/PR, and use the same numbering discipline without forcing a separate planning PR.

Prioritize cases that unit tests can prove. Before implementation, mark each case's verification method and identify integration or human/UI evidence that remains outside unit scope. Do not call storage/file-backed integration checks unit evidence. Do not add UI automation or CI UI jobs as part of this workflow unless separately requested. Deferring UI automation does not mark a UI requirement satisfied; report user-owned or unresolved acceptance honestly.

## Test and implement

For each unit-testable case covering genuinely new behavior or a concrete bug, write the test with meaningful assertions and record its natural failure before the smallest implementation change, then return Green. Existing correct behavior can begin Green. Never retroactively manufacture Red if implementation already exists; report the observed starting state honestly. Avoid duplicate tests merely to create another numbered artifact.

Include relevant normal, boundary and exceptional business scenarios. Set up failures through test inputs, fixtures or a controlled dependency, such as a storage double that returns a save error, then assert the required response and preserved state. An expected business failure should make the test pass when the implementation handles it correctly. Do not use unconditional failing assertions or change expected results to force failure.

Do not perform mutation testing: do not temporarily break correct production code or alter assertions/expectations to see whether an existing test detects the change. A plan saying a test must detect a particular defect calls for meaningful scenario assertions, not a destructive experiment. If a concrete coverage gap appears, add or strengthen the corresponding business-scenario test. Do not turn every test into another task to validate the test itself.

Stop when the accepted scenarios have adequate evidence and required project checks pass. Add further verification only for a specific unmet criterion, observed regression or new evidence; do not extend delivery through speculative test-validation cycles.

Include the acceptance case ID in the test name or framework display name so failures can be traced back to the checklist and contract. Normalize the ID for language identifiers when necessary, preserving a deterministic recoverable form, such as `MOVE_02_T03`. Do not add prohibited source comments. Existing adequate tests can receive the ID in their name/display metadata and be mapped instead of copied; do not claim unnamed tests satisfy the new tracing convention without a supported identifier mapping.

Maintain the mapping from contract clause to acceptance case to exact test identifier and observed result. A matching title is not proof: assertions must establish the case's expected outcome. Run declared project checks and report remaining non-unit evidence separately. The implementation reviewer checks both coverage of in-scope clauses and whether the actual assertions/code support the numbered cases. Worker verification makes no new product decisions.

Use declared lint/test/build entry points, respecting directory allowlists and platform-tool authorization. Passing exact-head evidence does not need repetition solely because another Agent reads it; rerun when changed code, missing or contradictory evidence, project policy or an observed defect warrants it.

Temporary local shared-package overrides are development tools, not portable delivery artifacts. Respect project policy for dependency publication and pinning. Do not infer that repository-owned local packages are invalid.

A PR report states what changed, why, which checks actually ran and their limits. Never promote intended checks, cached historical reports or contract assertions into a current passing result.
