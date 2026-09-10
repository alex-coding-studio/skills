# Delivery Contract

Use the project's existing document structure. A contract should let another Agent execute one accepted slice without reconstructing the planning conversation.

Include:

1. Outcome and task identity.
2. Frozen accepted source identity, readable evidence and revision/hash, plus a compact source-to-clause mapping; follow source-fidelity.md. Label working-tree evidence honestly.
3. In-scope behavior and explicit exclusions.
4. Stable rule/criterion IDs with unambiguous observable behavior, conditions, exclusions and exceptions. These define correctness; the Worker derives executable acceptance cases without redefining that meaning.
5. Verification method for each criterion, distinguishing automated checks, integration evidence and human acceptance.
6. Relevant architecture, compatibility and dependency constraints; do not specify types or algorithms without a real requirement.
7. Known applicable pitfalls and their sources.
8. Unresolved blockers and a change/expansion protocol.

Use representative cases where they establish accepted behavior; avoid speculative Cartesian-product test matrices. Do not add scope to make an assertion easy. Contract prose is not implementation evidence.

Specify relevant normal and exceptional business scenarios and their expected outcomes. Use TDD for new unit-observable behavior. Do not add mutation testing, deliberate corruption of correct implementation, or a requirement to demonstrate that each completed test fails after a code mutation. Describe the business condition to set up and the result to assert instead.

The contract itself cannot contain its own future merge SHA. Record source revisions in the document and bind the final document path to the actual merge SHA in the post-merge handoff.

Write for Agent execution rather than a second human-facing product narrative. Numbered clauses and compact mappings are appropriate; compression must not remove necessary context or introduce ambiguity. Preserve existing capability contracts and their IDs when the delivery slice references them instead of duplicating their authority.
