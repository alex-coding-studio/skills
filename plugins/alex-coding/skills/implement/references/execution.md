# Implementation Evidence

Read the narrow source closure from the accepted contract and relevant current code. Expand only to resolve an actual missing fact, affected caller or contradiction. Return product-meaning changes to Plan rather than writing a test that invents a requirement.

For unit-observable new behavior or a concrete bug, prefer a criterion-linked test and a natural failing result before the smallest implementation change. Existing correct behavior can begin green; do not change correct code or expected values merely to fabricate failure. Avoid tests that mirror implementation, assert constants or duplicate evidence without a requirement or regression risk.

Follow project-native naming and test conventions. Criterion IDs can be recorded in the project's accepted mapping rather than forcing one language's test syntax or one test per user journey. UI, integration, deployment, device and human-experience outcomes need evidence at their own boundary.

Use declared lint/test/build entry points, respecting directory allowlists and platform-tool authorization. Passing exact-head evidence does not need repetition solely because another Agent reads it; rerun when changed code, missing or contradictory evidence, project policy or an observed defect warrants it.

Temporary local shared-package overrides are development tools, not portable delivery artifacts. Respect project policy for dependency publication and pinning. Do not infer that repository-owned local packages are invalid.

A PR report states what changed, why, which checks actually ran and their limits. Never promote intended checks, cached historical reports or contract assertions into a current passing result.
