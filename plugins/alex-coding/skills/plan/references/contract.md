# Delivery Contract

Use the project's existing document structure. A contract should let another Agent execute one accepted slice without reconstructing the planning conversation.

Include:

1. Outcome and task identity.
2. Relevant context and authoritative source paths/revisions; label working-tree evidence honestly.
3. In-scope behavior and explicit exclusions.
4. Stable criterion IDs with observable acceptance, including negative outcomes only when the accepted requirement needs them.
5. Verification method for each criterion, distinguishing automated checks, integration evidence and human acceptance.
6. Relevant architecture, compatibility and dependency constraints; do not specify types or algorithms without a real requirement.
7. Known applicable pitfalls and their sources.
8. Unresolved blockers and a change/expansion protocol.

Use representative cases where they establish accepted behavior; avoid speculative Cartesian-product test matrices. Do not add scope to make an assertion easy. Contract prose is not implementation evidence.

The contract itself cannot contain its own future merge SHA. Record source revisions in the document and bind the final document path to the actual merge SHA in the post-merge handoff.
